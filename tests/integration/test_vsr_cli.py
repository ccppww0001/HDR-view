from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from hdrview.cli import main
from hdrview.color.icc import decode_with_icc
from hdrview.io.intermediate import read_intermediate, write_intermediate
from hdrview.model import ColorState, HdrImage
from hdrview.nvidia.vsr import VsrResult


def jpeg(path: Path, size=(8, 6), color=(30, 50, 70)) -> Path:
    Image.new("RGB", size, color).save(path, "JPEG")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hdr_for(sdr, source_hash):
    rgba = np.ones(sdr.rgba.shape, dtype=np.float32)
    return HdrImage(rgba, ColorState("bt2020", "linear"), 2.0, {
        "pipeline": "nvidia-truehdr", "source_sha256": source_hash, "nvidia-vfx": "0.2.0.0",
    })


def test_enhance_default_skips_vsr(tmp_path, monkeypatch):
    source = jpeg(tmp_path / "source.jpg")
    monkeypatch.setattr("hdrview.cli.run_vsr", lambda *args: pytest.fail("unexpected VSR"))
    monkeypatch.setattr("hdrview.cli.run_truehdr", lambda sdr, params, source_hash: hdr_for(sdr, source_hash))
    monkeypatch.setattr("hdrview.cli.export_hdr", lambda hdr, sdr, run_dir, stem, nits: {"target_nits": nits})

    assert main(["enhance-nvidia", str(source), "--output", str(tmp_path / "out")]) == 0
    report = json.loads((tmp_path / "out/run-001/report.json").read_text(encoding="utf-8"))
    assert report["vsr"] == {"executed": False}
    assert "sdr_base" not in report


def test_enhance_vsr_precedes_truehdr_and_persists_provenance(tmp_path, monkeypatch):
    source = jpeg(tmp_path / "source.jpg")
    derived = jpeg(tmp_path / "derived.jpg", (16, 12), (90, 80, 70))
    derived_sdr = decode_with_icc(derived.read_bytes())
    calls = []
    vsr_report = {"executed": True, "mode": "upscale", "scale": 2, "quality": "high", "strength": 1.0}

    def vsr(sdr, params, source_hash):
        calls.append("vsr")
        assert sdr.rgba.shape == (6, 8, 4)
        assert params.scale == 2 and source_hash == digest(source)
        return VsrResult(derived_sdr, vsr_report)

    def truehdr(sdr, params, source_hash):
        calls.append("truehdr")
        assert sdr.rgba.shape == (12, 16, 4)
        assert sdr.compressed_jpeg == derived.read_bytes()
        return hdr_for(sdr, source_hash)

    def export(hdr, sdr, run_dir, stem, nits):
        calls.append("export")
        assert hdr.rgba.shape == sdr.rgba.shape == (12, 16, 4)
        return {"target_nits": nits}

    monkeypatch.setattr("hdrview.cli.run_vsr", vsr)
    monkeypatch.setattr("hdrview.cli.run_truehdr", truehdr)
    monkeypatch.setattr("hdrview.cli.export_hdr", export)
    assert main(["enhance-nvidia", str(source), "--vsr", "--output", str(tmp_path / "out")]) == 0
    assert calls == ["vsr", "truehdr", "export"]
    run_dir = tmp_path / "out/run-001"
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    base = run_dir / "source-VSR-base.jpg"
    assert base.read_bytes() == derived.read_bytes()
    assert report["sdr_base"] == {"path": str(base), "sha256": digest(derived)}
    assert report["vsr"] == vsr_report
    intermediate = read_intermediate(run_dir / "source-truehdr")
    assert intermediate.rgba.shape == (12, 16, 4)
    assert intermediate.provenance["source_sha256"] == digest(source)
    assert intermediate.provenance["sdr_base_sha256"] == digest(derived)
    assert intermediate.provenance["vsr_applied"] is True
    assert report["intermediate"]["source_sha256"] == digest(source)


def test_enhance_vsr_only_writes_sdr_jpeg(tmp_path, monkeypatch):
    source = jpeg(tmp_path / "source.jpg")
    derived = jpeg(tmp_path / "derived.jpg", (16, 12))
    image = decode_with_icc(derived.read_bytes())
    monkeypatch.setattr("hdrview.cli.run_vsr", lambda *args: VsrResult(image, {"executed": True}))
    monkeypatch.setattr("hdrview.cli.run_truehdr", lambda *args: pytest.fail("unexpected HDR"))
    monkeypatch.setattr("hdrview.cli.export_hdr", lambda *args: pytest.fail("unexpected export"))
    assert main(["enhance-vsr", str(source), "--output", str(tmp_path / "out")]) == 0
    run_dir = tmp_path / "out/run-001"
    assert sorted(p.name for p in run_dir.iterdir()) == ["report.json", "source-VSR.jpg"]
    assert (run_dir / "source-VSR.jpg").read_bytes() == derived.read_bytes()
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["output_sha256"] == digest(derived)
    assert report["source_sha256"] == digest(source)


@pytest.mark.parametrize("command", ["enhance-vsr", "enhance-nvidia"])
def test_vsr_failure_does_not_create_output(tmp_path, monkeypatch, command):
    source = jpeg(tmp_path / "source.jpg")
    def fail(*args):
        raise RuntimeError("synthetic VSR failure")
    monkeypatch.setattr("hdrview.cli.run_vsr", fail)
    monkeypatch.setattr("hdrview.cli.run_truehdr", lambda *args: pytest.fail("unexpected HDR"))
    args = [command, str(source), "--output", str(tmp_path / "out")]
    if command == "enhance-nvidia":
        args.append("--vsr")
    with pytest.raises(RuntimeError, match="synthetic VSR failure"):
        main(args)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("option,value", [("--vsr-mode", "upscale"), ("--vsr-scale", "2"), ("--vsr-quality", "high"), ("--vsr-strength", "0.5")])
def test_vsr_options_require_vsr_flag(tmp_path, option, value):
    with pytest.raises(SystemExit) as error:
        main(["enhance-nvidia", str(tmp_path / "source.jpg"), "--output", str(tmp_path / "out"), option, value])
    assert error.value.code == 2
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("command", ["enhance-vsr", "enhance-nvidia"])
def test_denoise_rejects_explicit_scale(tmp_path, monkeypatch, command):
    source = jpeg(tmp_path / "source.jpg")
    monkeypatch.setattr("hdrview.cli.run_vsr", lambda *args: pytest.fail("unexpected VSR"))
    args = [command, str(source), "--vsr-mode", "denoise", "--vsr-scale", "2", "--output", str(tmp_path / "out")]
    if command == "enhance-nvidia":
        args.append("--vsr")
    with pytest.raises(ValueError, match="--vsr-scale"):
        main(args)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("case", ["missing_base", "wrong_hash", "missing_hash", "valid"])
def test_convert_vsr_intermediate_checks_derived_base(tmp_path, monkeypatch, case):
    source = jpeg(tmp_path / "source.jpg")
    base = jpeg(tmp_path / "base.jpg", (16, 12))
    wrong = jpeg(tmp_path / "wrong.jpg", (16, 12), (200, 40, 10))
    image = hdr_for(decode_with_icc(base.read_bytes()), digest(source))
    image.provenance["vsr_applied"] = True
    if case != "missing_hash":
        image.provenance["sdr_base_sha256"] = digest(base)
    intermediate = write_intermediate(image, tmp_path / "intermediate")
    args = ["convert-nvidia", str(source), "--intermediate", str(intermediate.stem), "--output", str(tmp_path / "out")]
    if case != "missing_base":
        args.extend(["--sdr-base", str(wrong if case == "wrong_hash" else base)])
    monkeypatch.setattr("hdrview.cli.run_vsr", lambda *args: pytest.fail("unexpected VSR"))
    monkeypatch.setattr("hdrview.cli.run_truehdr", lambda *args: pytest.fail("unexpected HDR"))
    def export(hdr, sdr, run_dir, stem, nits):
        assert sdr.compressed_jpeg == base.read_bytes()
        assert hdr.rgba.shape == sdr.rgba.shape == (12, 16, 4)
        return {"target_nits": nits}
    monkeypatch.setattr("hdrview.cli.export_hdr", export)
    if case != "valid":
        message = {"missing_base": "--sdr-base", "wrong_hash": "SHA-256", "missing_hash": "哈希"}[case]
        with pytest.raises(ValueError, match=message):
            main(args)
        assert not (tmp_path / "out").exists()
        return
    assert main(args) == 0
    report = json.loads((tmp_path / "out/run-001/report.json").read_text(encoding="utf-8"))
    assert report["gpu_executed"] is False
    assert report["vsr"] == {"executed": False, "intermediate_vsr_applied": True}
    assert report["sdr_base"]["sha256"] == digest(base)
    assert "intermediate" not in report


def test_verify_directory_excludes_vsr_base(tmp_path, monkeypatch, capsys):
    from dataclasses import dataclass
    from types import SimpleNamespace

    @dataclass
    class Inspection:
        hdr_capacity_max: float = 2.0

    base = jpeg(tmp_path / "source-VSR-base.jpg")
    result = jpeg(tmp_path / "source-UltraHDR-1000nit.jpg")
    inspected, decoded = [], []
    def inspect(path):
        inspected.append(path)
        return Inspection()
    def decode(path, boost):
        decoded.append((path, boost))
        return SimpleNamespace(rgba=np.zeros((6, 8, 4)))
    monkeypatch.setattr("hdrview.output.ultrahdr.inspect_ultrahdr", inspect)
    monkeypatch.setattr("hdrview.verify.roundtrip.decode_reference", decode)
    assert main(["verify", str(tmp_path)]) == 0
    assert inspected == [result]
    assert decoded == [(result, 1.0), (result, 2.0)]
    assert json.loads(capsys.readouterr().out)[0]["output"] == str(result)
    assert base.exists()


def test_verify_directory_rejects_only_vsr_base(tmp_path, monkeypatch):
    jpeg(tmp_path / "source-VSR-base.jpg")
    monkeypatch.setattr("hdrview.output.ultrahdr.inspect_ultrahdr", lambda *args: pytest.fail("unexpected inspection"))
    monkeypatch.setattr("hdrview.verify.roundtrip.decode_reference", lambda *args: pytest.fail("unexpected decode"))
    with pytest.raises(FileNotFoundError, match="没有可验证"):
        main(["verify", str(tmp_path)])
