from pathlib import Path

import numpy as np
import pytest

from hdrview.color.icc import decode_with_icc
from hdrview.vivo.auxiliary import extract_auxiliary_jpeg
from hdrview.vivo.container import inspect_jpeg
from hdrview.vivo.diagnostics import analyze_vivo_alignment

SAMPLE = Path(__file__).resolve().parents[2] / "images/fromthephone/IMG_20261111_175548.jpg"


@pytest.mark.skipif(not SAMPLE.is_file(), reason="私人原始样本不在工作区")
def test_real_vivo_auxiliary_has_spatially_sparse_highlights():
    document = inspect_jpeg(SAMPLE)
    primary = decode_with_icc(document.data[: document.vivo.primary_eoi_offset + 2]).rgba[..., :3].astype(np.float32) / 255
    auxiliary = decode_with_icc(extract_auxiliary_jpeg(document)).rgba[..., :3].astype(np.float32) / 255

    report = analyze_vivo_alignment(primary, auxiliary)

    assert report.primary_size == (4096, 3072)
    assert report.auxiliary_size == (2048, 1536)
    assert report.auxiliary_nonzero_fraction > 0
    assert report.auxiliary_nonzero_fraction < 0.2
    assert report.highlight_bbox is not None
