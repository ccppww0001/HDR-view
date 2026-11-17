from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from hdrview.cli import main
from hdrview.color.icc import decode_with_icc
from hdrview.io.intermediate import write_intermediate
from hdrview.model import ColorState, HdrImage
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

    result = inspect_ultrahdr(tmp_path / "out" / "run-001" / f"{source.stem}-UltraHDR-400nit.jpg")
    assert result.is_ultrahdr
    assert result.width == 4096
    assert result.gainmap_width > 0


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
