from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from hdrview.cli import main
from hdrview.color.icc import decode_with_icc
from hdrview.output.ultrahdr import inspect_ultrahdr
from hdrview.verify.roundtrip import decode_reference
from hdrview.vivo.container import inspect_jpeg

SAMPLES = Path(r"D:\MyProject\HDR-view\images\fromthephone")


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="私人原始样本不在工作区")
def test_vivo_candidate_exports_real_ultrahdr_and_preserves_sdr_base(tmp_path: Path):
    source = SAMPLES / "IMG_20261116_212648.jpg"
    before = source.read_bytes()

    assert main(["convert-vivo", str(source), "--output", str(tmp_path)]) == 0

    output_dir = tmp_path / "run-001"
    output = output_dir / "IMG_20261116_212648-UltraHDR.jpg"
    report = inspect_ultrahdr(output)
    payload = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert report.is_ultrahdr
    assert report.width == 4096 and report.height == 3072
    assert report.gainmap_width > 0
    assert report.hdr_capacity_max > 1
    assert payload[0]["xdr_appearance_verified"] is False
    assert "未验证" in payload[0]["status"]
    assert source.read_bytes() == before
    original = decode_with_icc(before[: inspect_jpeg(source).vivo.primary_eoi_offset + 2])
    base = decode_reference(output, 1.0)
    assert base.rgba.shape == original.rgba.shape
    # 官方编码/解码可能改变少量码值，但不得把 SDR 主图换成 PQ 或全图 HDR。
    assert float(np.median(base.rgba[..., 0])) < 0.3


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="私人原始样本不在工作区")
def test_plain_sdr_input_is_not_faked_into_ultrahdr(tmp_path: Path):
    from PIL import Image

    plain = tmp_path / "plain.jpg"
    Image.new("RGB", (32, 32), (40, 50, 60)).save(plain, "JPEG")

    with pytest.raises(Exception, match="没有 vivo"):
        main(["convert-vivo", str(plain), "--output", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


def test_vivo_path_does_not_contain_nvidia_provenance(tmp_path: Path):
    if not SAMPLES.is_dir():
        pytest.skip("私人原始样本不在工作区")
    main(["convert-vivo", str(SAMPLES / "IMG_20261116_212648.jpg"), "--output", str(tmp_path)])
    report = json.loads((tmp_path / "run-001" / "report.json").read_text(encoding="utf-8"))

    assert report[0]["pipeline"] == "vivo-private-highlight-candidate"
    assert "nvidia" not in json.dumps(report).lower()
