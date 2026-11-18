from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hdrview.cli import main
from hdrview.color.icc import decode_with_icc
from hdrview.output.ultrahdr import inspect_ultrahdr
from hdrview.verify.roundtrip import decode_reference
from hdrview.vivo.container import inspect_jpeg

SAMPLE = Path(__file__).resolve().parents[2] / "images/fromthephone/IMG_20261111_175548.jpg"


@pytest.mark.skipif(not SAMPLE.is_file(), reason="私人原始样本不在工作区")
def test_vivo_batch_skips_plain_jpeg_and_preserves_sdr_base(tmp_path: Path, capsys):
    inputs = tmp_path / "input photos"
    inputs.mkdir()
    source = inputs / SAMPLE.name
    source.write_bytes(SAMPLE.read_bytes())
    Image.new("RGB", (32, 32)).save(inputs / "plain.jpg")
    before = source.read_bytes()

    output_dir = tmp_path / "results"
    assert main(["convert-vivo", str(inputs), "--target-nits", "400", "1000", "--output-dir", str(output_dir)]) == 0
    assert "plain.jpg" in capsys.readouterr().out
    assert not any(output_dir.glob("plain*"))

    output = output_dir / "IMG_20261111_175548-UltraHDR-400nit.jpg"
    report = inspect_ultrahdr(output)
    payload = json.loads((output_dir / "IMG_20261111_175548-convert-vivo-report.json").read_text(encoding="utf-8"))
    assert report.is_ultrahdr
    assert report.width == 4096 and report.height == 3072
    assert report.gainmap_width > 0
    assert report.hdr_capacity_max == pytest.approx(400 / 203, rel=0.001)
    assert inspect_ultrahdr(output_dir / "IMG_20261111_175548-UltraHDR-1000nit.jpg").hdr_capacity_max == pytest.approx(1000 / 203, rel=0.001)
    jxr_path = output_dir / "IMG_20261111_175548-HDR-400nit.jxr"
    assert jxr_path.is_file()
    from hdrview.output.jxr import decode_jxr
    jxr = decode_jxr(jxr_path)
    assert jxr.rgba.shape == (3072, 4096, 4)
    records = {item["target_nits"]: item for item in payload["outputs"]}
    assert records[400]["display_mapping"] == "hdr400-highlight-compression"
    assert records[400]["hdr_capacity_max"] == pytest.approx(400 / 203, rel=0.001)
    assert records[400]["jpeg_xr"]["native_float"] is True
    assert records[400]["jpeg_xr"]["windows_photos_hdr_verified"] is False
    assert "hdr_capacity_max" not in records[400]["jpeg_xr"]
    assert records[1000]["display_mapping"] == "none"
    assert records[1000]["hdr_capacity_max"] == pytest.approx(1000 / 203, rel=0.001)
    assert "jpeg_xr" not in records[1000]
    assert payload["xdr_appearance_verified"] is False
    assert "未验证" in payload["status"]
    assert source.read_bytes() == before
    original = decode_with_icc(before[: inspect_jpeg(source).vivo.primary_eoi_offset + 2])
    base = decode_reference(output, 1.0)
    assert base.rgba.shape == original.rgba.shape
    # 官方编码/解码可能改变少量码值，但不得把 SDR 主图换成 PQ 或全图 HDR。
    assert float(np.median(base.rgba[..., 0])) < 0.3


def test_plain_sdr_input_is_not_faked_into_ultrahdr(tmp_path: Path):
    plain = tmp_path / "plain.jpg"
    Image.new("RGB", (32, 32), (40, 50, 60)).save(plain, "JPEG")

    with pytest.raises(Exception, match="没有 vivo"):
        main(["convert-vivo", str(plain), "--output", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


def test_verify_writes_json_without_raw_pixel_arrays(tmp_path: Path):
    if not SAMPLE.is_file():
        pytest.skip("私人原始样本不在工作区")
    source = SAMPLE
    main(["convert-vivo", str(source), "--target-nits", "400", "--output", str(tmp_path)])
    output = tmp_path / "IMG_20261111_175548-UltraHDR-400nit.jpg"
    report_path = tmp_path / "verification.json"
    assert main(["verify", str(output), "--json", str(report_path)]) == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))[0]["hdr_capacity_max"] == pytest.approx(400 / 203, rel=0.001)


def test_vivo_path_does_not_contain_nvidia_provenance(tmp_path: Path):
    if not SAMPLE.is_file():
        pytest.skip("私人原始样本不在工作区")
    main(["convert-vivo", str(SAMPLE), "--output", str(tmp_path)])
    report = json.loads((tmp_path / "IMG_20261111_175548-convert-vivo-report.json").read_text(encoding="utf-8"))

    assert report["pipeline"] == "vivo-private-highlight-candidate"
    assert "nvidia" not in json.dumps(report).lower()
    assert [item["target_nits"] for item in report["outputs"]] == [1000]
    assert report["outputs"][0]["display_mapping"] == "none"
    assert not list((tmp_path).glob("*400nit*"))
