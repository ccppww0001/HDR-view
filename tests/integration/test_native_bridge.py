from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from hdrview.model import ColorState, HdrImage
from hdrview.io.intermediate import write_intermediate
import numpy as np


@pytest.fixture()
def hdr_input(tmp_path: Path):
    rgba = np.ones((2, 3, 4), dtype=np.float32)
    image = HdrImage(
        rgba=rgba,
        color=ColorState("bt2020", "linear"),
        hdr_capacity_max=1.0,
        provenance={"source_sha256": "a" * 64, "pipeline": "synthetic"},
    )
    return write_intermediate(image, tmp_path / "input")


def test_bridge_rejects_missing_sidecar_before_running(tmp_path: Path):
    script = Path("src/hdrview/build/Build-Native.ps1")
    assert script.is_file()
    raw = tmp_path / "input.f16rgba"
    raw.write_bytes(b"pixels")

    from hdrview.output.ultrahdr import encode_with_bridge

    with pytest.raises(FileNotFoundError):
        encode_with_bridge(tmp_path / "missing.exe", raw, tmp_path / "missing.json", tmp_path / "sdr.jpg", tmp_path / "out.jpg")


def test_bridge_refuses_existing_output(tmp_path: Path, hdr_input):
    executable = tmp_path / "fake.exe"
    executable.write_bytes(b"not executable")
    sdr = tmp_path / "sdr.jpg"
    sdr.write_bytes(b"not real jpeg")
    output = tmp_path / "out.jpg"
    output.write_bytes(b"keep")

    from hdrview.output.ultrahdr import encode_with_bridge

    with pytest.raises(FileExistsError):
        encode_with_bridge(executable, hdr_input.pixel, hdr_input.metadata, sdr, output)
    assert output.read_bytes() == b"keep"


def test_build_script_requires_an_explicit_tool_directory():
    script = Path("src/hdrview/build/Build-Native.ps1")
    env = dict(os.environ)
    env.pop("HDRVIEW_TOOL_DIR", None)

    result = subprocess.run(["pwsh", "-NoProfile", "-File", str(script), "-Test"], capture_output=True, text=True, env=env)

    assert result.returncode != 0
    assert "HDRVIEW_TOOL_DIR" in result.stdout + result.stderr
