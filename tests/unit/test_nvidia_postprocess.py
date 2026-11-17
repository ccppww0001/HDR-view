from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from hdrview.color.transfer import pq_to_linear_bt2020
from hdrview.io.intermediate import read_intermediate
from hdrview.nvidia.postprocess import read_truehdr_output


def test_truehdr_pq_output_is_decoded_to_shared_linear_units():
    # 1.0 PQ = 10000 nit；共享中间单位为 203 nit 的倍数。
    pq = np.array([1.0], dtype=np.float32)
    assert pq_to_linear_bt2020(pq)[0] / 203 == pytest.approx(10000 / 203, rel=1e-6)


def test_truehdr_intermediate_rejects_hash_mismatch(tmp_path: Path):
    from hdrview.model import ColorState, HdrImage
    from hdrview.io.intermediate import write_intermediate

    rgba = np.zeros((1, 1, 4), dtype=np.float32)
    rgba[..., 3] = 1
    image = HdrImage(rgba, ColorState("bt2020", "linear"), 2.0, {"source_sha256": "a" * 64, "pipeline": "nvidia-truehdr"})
    paths = write_intermediate(image, tmp_path / "output")

    with pytest.raises(ValueError, match="SHA-256"):
        read_truehdr_output(paths.stem, expected_source_sha256="b" * 64)


def test_truehdr_intermediate_reads_valid_source(tmp_path: Path):
    from hdrview.model import ColorState, HdrImage
    from hdrview.io.intermediate import write_intermediate

    rgba = np.ones((1, 1, 4), dtype=np.float32)
    image = HdrImage(rgba, ColorState("bt2020", "linear"), 2.0, {"source_sha256": "a" * 64, "pipeline": "nvidia-truehdr"})
    paths = write_intermediate(image, tmp_path / "output")

    restored = read_truehdr_output(paths.stem, expected_source_sha256="a" * 64)

    assert restored.provenance["pipeline"] == "nvidia-truehdr"
    assert restored.color.transfer == "linear"
