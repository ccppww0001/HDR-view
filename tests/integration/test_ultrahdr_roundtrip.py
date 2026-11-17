from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageCms

from hdrview.model import ColorState, HdrImage, SdrImage
from hdrview.output.ultrahdr import encode_ultrahdr, inspect_ultrahdr
from hdrview.verify.roundtrip import decode_reference


@pytest.fixture()
def known_pair():
    sdr_rgba = np.zeros((64, 64, 4), dtype=np.uint8)
    sdr_rgba[..., :3] = 64
    sdr_rgba[..., 3] = 255
    image = Image.fromarray(sdr_rgba[..., :3], "RGB")
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=100, subsampling=0, icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    sdr = SdrImage(sdr_rgba, ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes(), buffer.getvalue())
    hdr_rgba = np.zeros((64, 64, 4), dtype=np.float32)
    hdr_rgba[..., :3] = (64 / 255) ** 2.2
    hdr_rgba[24:40, 24:40, :3] *= 4
    hdr_rgba[..., 3] = 1
    hdr = HdrImage(hdr_rgba, ColorState("bt2020", "linear"), 4.0, {"source_sha256": "b" * 64, "pipeline": "synthetic"})
    return hdr, sdr


def test_known_hdr_becomes_standard_ultrahdr_with_sdr_base(tmp_path: Path, known_pair):
    hdr, sdr = known_pair
    output = tmp_path / "known-ultrahdr.jpg"

    report = encode_ultrahdr(hdr, sdr, output)

    assert report.output == output
    assert report.is_ultrahdr is True
    assert report.width == 64 and report.height == 64
    assert report.gainmap_width > 0 and report.gainmap_height > 0
    assert report.hdr_capacity_max > 1
    data = output.read_bytes()
    assert b"hdrgm" in data or b"urn:iso:std:iso:ts:21496" in data
    assert b"MPF" in data
    report_path = None
    # 独立检查显式使用临时目录，避免输出中混入提取的 JPEG。
    from hdrview.output.ultrahdr import inspect_ultrahdr
    inspect_ultrahdr(output)
    # 容器重排是允许的；比较解码像素而非原始 JPEG 字节。
    extracted_base = sdr.compressed_jpeg
    original = Image.open(BytesIO(sdr.compressed_jpeg)).convert("RGB")
    repacked = Image.open(BytesIO(extracted_base)).convert("RGB")
    assert np.max(np.abs(np.asarray(original, dtype=np.int16) - np.asarray(repacked, dtype=np.int16))) <= 1
    with Image.open(output) as base:
        assert base.size == (64, 64)
        assert np.asarray(base)[0, 0, 0] == pytest.approx(64, abs=2)


def test_reference_decoder_respects_display_boost(tmp_path: Path, known_pair):
    hdr, sdr = known_pair
    output = tmp_path / "known-ultrahdr.jpg"
    encode_ultrahdr(hdr, sdr, output)

    sdr_decoded = decode_reference(output, display_boost=1.0)
    hdr_decoded = decode_reference(output, display_boost=inspect_ultrahdr(output).hdr_capacity_max)

    assert hdr_decoded.rgba[32, 32, 0] == pytest.approx(hdr.rgba[32, 32, 0], rel=0.12)
    assert hdr_decoded.rgba[32, 32, 0] > sdr_decoded.rgba[32, 32, 0] * 2
    assert hdr_decoded.rgba[0, 0, 0] == pytest.approx(sdr_decoded.rgba[0, 0, 0], rel=0.08)
    assert hdr_decoded.rgba[32, 32, 0] < 65504


def test_input_dimension_mismatch_is_rejected(tmp_path: Path, known_pair):
    hdr, sdr = known_pair
    wrong = SdrImage(sdr.rgba[:32, :32].copy(), sdr.icc, sdr.compressed_jpeg)
    with pytest.raises(ValueError):
        encode_ultrahdr(hdr, wrong, tmp_path / "bad.jpg")


def test_manual_gainmap_metadata_cannot_override_actual_ratio(tmp_path: Path, known_pair):
    hdr, sdr = known_pair
    hdr.provenance["gainmap_max_override"] = 100.0

    overridden = encode_ultrahdr(hdr, sdr, tmp_path / "override.jpg")
    hdr.provenance["gainmap_max_override"] = 1.0
    control = encode_ultrahdr(hdr, sdr, tmp_path / "control.jpg")

    # 官方容量可因线性输入默认 10000 nit 而大于 4；伪字段不能影响它。
    assert overridden.hdr_capacity_max == control.hdr_capacity_max
