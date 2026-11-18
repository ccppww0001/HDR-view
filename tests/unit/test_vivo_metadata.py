from __future__ import annotations

import json
import struct
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageCms

from hdrview.errors import InvalidVivoDataError
from hdrview.vivo.auxiliary import classify_support, extract_auxiliary_jpeg
from hdrview.vivo.container import inspect_jpeg
from hdrview.vivo.metadata import parse_vivo_metadata
from tests.unit.test_vivo_container import synthetic_jpeg, vivo_trailer

SAMPLES = Path(__file__).resolve().parents[2] / "images/fromthephone"


def display_p3_profile() -> bytes:
    sample = SAMPLES / "IMG_20261111_175548.jpg"
    if not sample.is_file():
        pytest.skip("构造 Display-P3 夹具需要原始样本的色彩配置")
    with Image.open(sample) as phone_image:
        return phone_image.info["icc_profile"]


def valid_jpeg(width: int = 4096, height: int = 3072, *, display_p3: bool = True) -> bytes:
    image = Image.new("RGB", (width, height), (20, 30, 40))
    buffer = BytesIO()
    if display_p3:
        icc = display_p3_profile()
    else:
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    image.save(buffer, format="JPEG", icc_profile=icc)
    return buffer.getvalue()


def sample_document(tmp_path: Path, auxiliary: bytes | None = None, model: str = "iQOO Neo9 Pro"):
    buffer = BytesIO()
    image = Image.new("RGB", (4096, 3072), (20, 30, 40))
    # Pillow 的 JpegImageFile.getexif 只在实际 EXIF 存在时报告相机字段。
    exif = Image.Exif()
    exif[0x010F] = "vivo"
    exif[0x0110] = model
    image.save(buffer, format="JPEG", exif=exif, icc_profile=display_p3_profile())
    path = tmp_path / "photo.jpg"
    path.write_bytes(buffer.getvalue() + b"streamdata" + (auxiliary or valid_jpeg(2048, 1536)) + vivo_trailer(b"")[len(b"streamdata"):])
    return inspect_jpeg(path)


@pytest.mark.parametrize("max_gain", [4.5, 0.6358773])
def test_metadata_reads_max_gain_without_calling_it_standard_gainmap(max_gain):
    payload = json.dumps({"com.vivo.xdr.maxGain": max_gain, "version": 2014}).encode()
    raw = b"streamcount\x00\x01vivo" + payload + b"\x00suffix"

    metadata = parse_vivo_metadata(raw)

    assert metadata.max_gain == max_gain
    assert metadata.json["version"] == 2014


def test_metadata_rejects_missing_or_invalid_json():
    for raw in [b"no json", b'vivo{"com.vivo.xdr.maxGain":NaN}', b'vivo{"com.vivo.xdr.maxGain":0}', b'vivo{"com.vivo.xdr.maxGain":-1}', b'vivo{"com.vivo.xdr.maxGain":1000000}', b'vivo{broken}']:
        with pytest.raises(InvalidVivoDataError):
            parse_vivo_metadata(raw)


def test_auxiliary_extraction_uses_trailer_offsets(tmp_path: Path):
    document = sample_document(tmp_path)

    auxiliary = extract_auxiliary_jpeg(document)

    with Image.open(BytesIO(auxiliary)) as image:
        assert image.size == (2048, 1536)
    assert document.vivo is not None
    assert document.vivo.data_length == len(auxiliary)


def test_supported_neo9_structure_is_accepted(tmp_path: Path):
    status = classify_support(sample_document(tmp_path))

    assert status.supported is True


def test_other_model_is_explicitly_unverified(tmp_path: Path):
    status = classify_support(sample_document(tmp_path, model="other vivo"))

    assert status.supported is False
    assert "未验证" in status.reason


def test_missing_vivo_trailer_is_not_treated_as_supported(tmp_path: Path):
    path = tmp_path / "plain.jpg"
    path.write_bytes(valid_jpeg(32, 32, display_p3=False))

    status = classify_support(inspect_jpeg(path))

    assert status.supported is False
    assert "没有 vivo" in status.reason


def test_auxiliary_size_mismatch_is_rejected(tmp_path: Path):
    status = classify_support(sample_document(tmp_path, auxiliary=valid_jpeg(1024, 768)))

    assert status.supported is False
    assert "尺寸" in status.reason


def test_non_p3_icc_is_explicitly_rejected(tmp_path: Path):
    status = classify_support(sample_document(tmp_path, auxiliary=valid_jpeg(2048, 1536, display_p3=False)))

    assert status.supported is False
    assert "Display-P3" in status.reason


@pytest.mark.parametrize(
    "filename,max_gain,auxiliary_size",
    [
        ("IMG_20261111_175548.jpg", 4.5, 840856),
        ("IMG_20261111_175601.jpg", 4.5, 870151),
        ("IMG_20261116_212648.jpg", 1.3358011, 708062),
        ("IMG_20261116_212653.jpg", 1.5154562, 708958),
        ("IMG_20261118_124523.jpg", 0.6358773, 1020014),
    ],
)
def test_real_neo9_samples(filename: str, max_gain: float, auxiliary_size: int):
    sample = SAMPLES / filename
    if not sample.is_file():
        pytest.skip("原始私人样本不在此工作区")
    document = inspect_jpeg(sample)

    assert classify_support(document).supported is True
    assert document.vivo is not None
    assert document.vivo.data_length == auxiliary_size
    assert parse_vivo_metadata(document.data[document.vivo.info_offset :]).max_gain == max_gain
