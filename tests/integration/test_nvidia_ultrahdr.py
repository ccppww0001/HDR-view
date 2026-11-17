from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from hdrview.cli import main
from hdrview.color.icc import decode_with_icc
from hdrview.io.intermediate import write_intermediate
from hdrview.io.intermediate import read_intermediate
from hdrview.model import ColorState, HdrImage, SdrImage
from hdrview.nvidia.runtime import TrueHdrParams
from hdrview.output.ultrahdr import inspect_ultrahdr

SAMPLES = Path(r"D:\MyProject\HDR-view\images\fromthephone")


def synthetic_nvidia_intermediate(tmp_path: Path, source: Path):
    sdr = decode_with_icc(source.read_bytes())
    linear = srgb = sdr.rgba[..., :3].astype(np.float32) / 255
    linear = np.where(linear <= 0.04045, linear / 12.92, ((linear + 0.055) / 1.055) ** 2.4)
    rgba = np.concatenate([linear * 1.2, np.ones((*linear.shape[:2], 1), dtype=np.float32)], axis=-1).astype(np.float32)
    from hdrview.color.gamut import rec709_to_bt2020
    rgba[..., :3] = rec709_to_bt2020(rgba[..., :3])
    from hashlib import sha256
    image = HdrImage(rgba, ColorState("bt2020", "linear"), 1.2, {"source_sha256": sha256(source.read_bytes()).hexdigest(), "pipeline": "nvidia-truehdr", "luminance": 400})
    return write_intermediate(image, tmp_path / "truehdr")


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="私人原始样本不在工作区")
def test_nvidia_intermediate_exports_standard_ultrahdr(tmp_path: Path):
    source = SAMPLES / "IMG_20261116_212648.jpg"
    intermediate = synthetic_nvidia_intermediate(tmp_path, source)

    assert main(["convert-nvidia", str(source), "--intermediate", str(intermediate.stem), "--output", str(tmp_path / "out")]) == 0

    run_dir = tmp_path / "out" / "run-001"
    result = inspect_ultrahdr(run_dir / f"{source.stem}-UltraHDR-1000nit.jpg")
    assert result.is_ultrahdr
    assert result.width == 4096
    assert result.gainmap_width > 0
    assert result.hdr_capacity_max == pytest.approx(1000 / 203, rel=0.001)
    assert not list(run_dir.glob("*400nit*"))
    report = json.loads((tmp_path / "out" / "run-001" / "report.json").read_text(encoding="utf-8"))
    assert [item["target_nits"] for item in report["outputs"]] == [1000]
    assert [item["display_mapping"] for item in report["outputs"]] == ["none"]
    assert report["gpu_executed"] is False
    assert "intermediate" not in report


def test_enhance_nvidia_missing_dependency_creates_no_output_directory(tmp_path: Path, monkeypatch):
    from PIL import Image
    source = tmp_path / "source.jpg"
    Image.new("RGB", (32, 32), (40, 50, 60)).save(source, "JPEG")
    output = tmp_path / "nvidia-output"

    def fail_before_model(sdr: SdrImage, params: TrueHdrParams, source_sha256: str):
        raise RuntimeError("nvidia-vfx==0.2.0.0 不存在")

    monkeypatch.setattr("hdrview.cli.run_truehdr", fail_before_model)
    with pytest.raises(RuntimeError, match="nvidia-vfx"):
        main(["enhance-nvidia", str(source), "--output", str(output)])
    assert not output.exists()


def test_enhance_nvidia_forwards_explicit_parameters(tmp_path: Path, monkeypatch):
    from PIL import Image
    source = tmp_path / "source.jpg"
    Image.new("RGB", (32, 32), (40, 50, 60)).save(source, "JPEG")
    received = {}

    def fail_before_output(sdr: SdrImage, params: TrueHdrParams, source_sha256: str):
        received.update(vars(params))
        received["source_sha256"] = source_sha256
        raise RuntimeError("合成运行器：没有执行 GPU")

    monkeypatch.setattr("hdrview.cli.run_truehdr", fail_before_output)
    with pytest.raises(RuntimeError, match="没有执行 GPU"):
        main(["enhance-nvidia", str(source), "--output", str(tmp_path / "out"), "--contrast", "110", "--saturation", "90", "--middle-gray", "55", "--luminance", "1200", "--no-debanding"])
    assert received["contrast"] == 110
    assert received["saturation"] == 90
    assert received["middle_gray"] == 55
    assert received["luminance"] == 1200
    assert received["debanding"] is False
    assert len(received["source_sha256"]) == 64
    assert not (tmp_path / "out").exists()


def test_enhance_nvidia_persists_intermediate_and_reports_actual_provenance(tmp_path: Path, monkeypatch):
    from PIL import Image
    source = tmp_path / "source.jpg"
    Image.new("RGB", (32, 32), (40, 50, 60)).save(source, "JPEG")
    rgba = np.full((32, 32, 4), 2.5, dtype=np.float32)
    rgba[..., 3] = 1.0
    hdr = HdrImage(
        rgba,
        ColorState("bt2020", "linear"),
        2.75,
        {"pipeline": "nvidia-truehdr", "source_sha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(), "nvidia-vfx": "0.2.0.0", "content_hdr_capacity_max": 2.75},
    )

    monkeypatch.setattr("hdrview.cli.run_truehdr", lambda sdr, params, source_sha256: hdr)
    monkeypatch.setattr("hdrview.cli.export_hdr", lambda hdr, sdr, run_dir, stem, target_nits: {"target_nits": target_nits})

    assert main(["enhance-nvidia", str(source), "--output", str(tmp_path / "out")]) == 0

    run_dir = tmp_path / "out" / "run-001"
    intermediate = read_intermediate(run_dir / "source-truehdr")
    np.testing.assert_array_equal(intermediate.rgba, rgba.astype(np.float16).astype(np.float32))
    assert intermediate.hdr_capacity_max == 2.75
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["intermediate"] == {
        "pixel": str(run_dir / "source-truehdr.f16rgba"),
        "metadata": str(run_dir / "source-truehdr.json"),
        "source_sha256": report["source_sha256"],
    }
    assert report["nvidia_vfx"] == "0.2.0.0"
    assert report["content_hdr_capacity_max"] == 2.75
    assert report["truehdr_params"] == vars(TrueHdrParams())
    assert report["gpu_executed"] is True
    assert report["outputs"] == [{"target_nits": 1000}]


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="私人原始样本不在工作区")
def test_nvidia_hash_mismatch_is_rejected(tmp_path: Path):
    source = SAMPLES / "IMG_20261116_212648.jpg"
    intermediate = synthetic_nvidia_intermediate(tmp_path, source)
    metadata = intermediate.metadata.read_text(encoding="utf-8").replace(intermediate.stem.name, intermediate.stem.name)
    import json
    payload = json.loads(metadata)
    payload["provenance"]["source_sha256"] = "0" * 64
    intermediate.metadata.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        main(["convert-nvidia", str(source), "--intermediate", str(intermediate.stem), "--output", str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()


def test_avif_writer_does_not_claim_full_hdr10_mastering(tmp_path: Path):
    from hdrview.model import ColorState, HdrImage
    from hdrview.output.avif import save_avif_pq

    rgba = np.ones((1, 1, 4), dtype=np.float32)
    image = HdrImage(rgba, ColorState("bt2020", "linear"), 2.0, {"source_sha256": "a" * 64})

    with pytest.raises((NotImplementedError, RuntimeError)):
        save_avif_pq(image, tmp_path / "out.avif", peak_nits=400)
