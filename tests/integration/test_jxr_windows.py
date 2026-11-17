from __future__ import annotations

from pathlib import Path
import json
import subprocess

import numpy as np
import pytest

from hdrview.errors import InvalidIntermediateError
from hdrview.io.intermediate import write_intermediate
from hdrview.model import ColorState, HdrImage
from hdrview.output.jxr import decode_jxr, default_bridge, encode_jxr


pytestmark = pytest.mark.skipif(not __import__("sys").platform.startswith("win"), reason="JPEG XR 测试需要 Windows WIC")


def _sample_hdr() -> HdrImage:
    rgba = np.zeros((16, 16, 4), dtype=np.float32)
    rgba[..., :3] = (2.0, 1.0, 0.5)
    rgba[..., 3] = 1.0
    return HdrImage(
        rgba=rgba,
        color=ColorState("bt2020", "linear"),
        hdr_capacity_max=2.0,
        provenance={"source_sha256": "c" * 64, "pipeline": "synthetic-jxr"},
    )


def test_wic_jxr_native_float_roundtrip(tmp_path: Path):
    output = tmp_path / "highlight.jxr"

    report = encode_jxr(_sample_hdr(), output)

    assert output.is_file() and output.stat().st_size > 0
    assert report["width"] == 16 and report["height"] == 16
    assert report["native_pixel_format"] == "GUID_WICPixelFormat64bppRGBAHalf"
    assert report["native_float"] is True
    assert report["windows_photos_hdr_verified"] is False
    assert report["hdr_capacity_max"] == 1.0
    assert report["jxr_sha256"] == __import__("hashlib").sha256(output.read_bytes()).hexdigest()
    assert "source_sha256" not in report
    assert report["native_content_max"] > 2.0
    # 16×16 是有损编码验证样本；高光必须明显超过 SDR，精确像素误差在下面限定。
    assert report["content_max_bt2020"] > 1.5

    decoded = decode_jxr(output)
    assert decoded.color == ColorState("bt2020", "linear", 203.0)
    assert decoded.rgba.shape == (16, 16, 4)
    assert np.all(np.isfinite(decoded.rgba))
    assert np.all(decoded.rgba >= 0)
    np.testing.assert_array_equal(decoded.rgba[..., 3], np.ones((16, 16), dtype=np.float32))
    # 实测最大绝对误差约 0.000308；0.001/0.002 留少量浮点裕量，同时可检出矩阵转置和通道串扰。
    np.testing.assert_allclose(decoded.rgba[8, 8, :3], _sample_hdr().rgba[8, 8, :3], rtol=0.002, atol=0.001)
    assert decoded.rgba[8, 8, 0] > decoded.rgba[8, 8, 1] > decoded.rgba[8, 8, 2]
    assert decoded.provenance["source_sha256"] == __import__("hashlib").sha256(output.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("name", "rgb"),
    [
        ("neutral-sdr", (0.5, 0.5, 0.5)),
        ("white-sdr", (1.0, 1.0, 1.0)),
        ("white-hdr", (2.0, 2.0, 2.0)),
        ("saturated-bt2020", (0.25, 1.5, 0.1)),
    ],
)
def test_wic_jxr_color_patches_have_bounded_error(tmp_path: Path, name, rgb):
    rgba = np.empty((16, 16, 4), dtype=np.float32)
    rgba[..., :3] = rgb
    rgba[..., 3] = 1.0
    image = HdrImage(
        rgba,
        ColorState("bt2020", "linear"),
        2.0,
        {"source_sha256": "c" * 64, "pipeline": "synthetic-color-patch"},
    )

    encode_jxr(image, output := tmp_path / f"{name}.jxr")
    decoded = decode_jxr(output)

    # 这些固定色块的实测最大绝对误差约 0.000308，严格界限防止用容差掩盖色彩错误。
    np.testing.assert_allclose(decoded.rgba[8, 8, :3], np.asarray(rgb, dtype=np.float32), rtol=0.002, atol=0.001)


@pytest.mark.parametrize(
    "damage",
    [
        lambda metadata: metadata.replace('"schema": 1,', '"schema": 10,'),
        lambda metadata: metadata.replace('"sdr_white_nits": 203.0,', '"sdr_white_nits": "203junk",'),
        lambda metadata: metadata.replace('"primaries": "bt2020",', '"primaries": "bt2020junk",'),
        lambda metadata: metadata.replace('"provenance": {', '"provenance": {"width": 1,'),
        lambda metadata: metadata.replace('"provenance": {', '"provenance": {"primaries": "rec709",'),
        lambda metadata: metadata.replace('"provenance": {', '"provenance": {"sdr_white_nits": 80.0,'),
    ],
)
def test_native_bridge_rejects_corrupt_sidecar_without_output(tmp_path: Path, damage):
    intermediate = write_intermediate(_sample_hdr(), tmp_path / "input")
    damaged = damage(intermediate.metadata.read_text(encoding="utf-8"))
    assert damaged != intermediate.metadata.read_text(encoding="utf-8")
    json.loads(damaged)  # 每个用例都是合法 JSON，确保由 native 严格契约而非语法错误拒绝。
    intermediate.metadata.write_text(damaged, encoding="utf-8")
    output = tmp_path / "corrupt.jxr"

    result = subprocess.run(
        [str(default_bridge()), "encode", "--hdr", str(intermediate.pixel), "--meta", str(intermediate.metadata), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()
    assert not Path(str(output) + ".tmp").exists()


def test_native_bridge_rejects_nested_schema_name_without_output(tmp_path: Path):
    intermediate = write_intermediate(_sample_hdr(), tmp_path / "input")
    metadata = json.loads(intermediate.metadata.read_text(encoding="utf-8"))
    metadata["schema"] = 10
    metadata["provenance"]["schema"] = 1
    intermediate.metadata.write_text(json.dumps(metadata), encoding="utf-8")
    output = tmp_path / "nested-schema.jxr"

    result = subprocess.run(
        [str(default_bridge()), "encode", "--hdr", str(intermediate.pixel), "--meta", str(intermediate.metadata), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not output.exists()
    assert not Path(str(output) + ".tmp").exists()



def test_jxr_refuses_to_overwrite_output(tmp_path: Path):
    output = tmp_path / "existing.jxr"
    output.write_bytes(b"keep-existing-output")

    with pytest.raises(FileExistsError):
        encode_jxr(_sample_hdr(), output)

    assert output.read_bytes() == b"keep-existing-output"


def test_jxr_rejects_nonfinite_input_before_encoding(tmp_path: Path):
    image = _sample_hdr()
    image.rgba[0, 0, 0] = np.nan
    output = tmp_path / "invalid.jxr"

    with pytest.raises(InvalidIntermediateError):
        encode_jxr(image, output)

    assert not output.exists()
