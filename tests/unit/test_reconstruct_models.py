from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from hdrview.vivo.auxiliary import extract_auxiliary_jpeg
from hdrview.vivo.container import inspect_jpeg
from hdrview.vivo.diagnostics import analyze_vivo_alignment
from hdrview.vivo.reconstruct import ReconstructionParams, reconstruct


def synthetic_auxiliary(primary: np.ndarray) -> bytes:
    from PIL import Image
    from io import BytesIO

    buffer = BytesIO()
    Image.fromarray(primary.astype(np.uint8)).save(buffer, "JPEG")
    return buffer.getvalue()


def test_alignment_reports_half_resolution_geometry_and_zero_highlights():
    primary = np.zeros((16, 16), dtype=np.float32)
    auxiliary = np.zeros((8, 8), dtype=np.float32)

    report = analyze_vivo_alignment(primary, auxiliary)

    assert report.primary_size == (16, 16)
    assert report.auxiliary_size == (8, 8)
    assert report.auxiliary_nonzero_fraction == 0
    assert report.auxiliary_luminance_max == 0


def test_alignment_detects_localized_highlight_not_global_brightness():
    primary = np.full((16, 16), 0.2, dtype=np.float32)
    auxiliary = np.zeros((8, 8), dtype=np.float32)
    auxiliary[3:5, 3:5] = 1

    report = analyze_vivo_alignment(primary, auxiliary)

    assert 0 < report.auxiliary_nonzero_fraction < 0.2
    assert report.highlight_center == pytest.approx((3.5, 3.5), abs=0.1)
    assert report.highlight_bbox == (3, 3, 5, 5)


def test_alignment_rejects_spatially_shifted_highlights():
    primary = np.zeros((16, 16), dtype=np.float32)
    primary[2:5, 2:5] = 1
    auxiliary = np.zeros((8, 8), dtype=np.float32)
    auxiliary[5:8, 5:8] = 1

    report = analyze_vivo_alignment(primary, auxiliary)

    assert report.highlight_overlap_fraction == 0


def test_candidate_reconstruction_returns_original_when_auxiliary_is_black():
    primary = np.array([[0.0, 0.1], [0.4, 0.8]], dtype=np.float32)
    auxiliary = np.zeros((1, 1), dtype=np.float32)

    result = reconstruct(primary, auxiliary, ReconstructionParams(model="additive-residual", scale=4.0, max_gain_cap=4.5, highlight_threshold=0.02))

    np.testing.assert_allclose(result, primary)
    assert np.all(np.isfinite(result))


def test_candidate_reconstruction_does_not_create_nan_or_global_shadow_gain():
    primary = np.array([[0.0, 0.1], [0.4, 0.8]], dtype=np.float32)
    auxiliary = np.array([[1.0]], dtype=np.float32)

    for model in ("additive-residual", "ratio", "short-exposure"):
        result = reconstruct(primary, auxiliary, ReconstructionParams(model=model, scale=1.0, max_gain_cap=4.5, highlight_threshold=0.02))
        assert np.all(np.isfinite(result))
        assert np.all(result >= primary)
        assert result[0, 0] == pytest.approx(primary[0, 0])


def test_candidate_reconstruction_is_continuous_across_highlight_threshold():
    primary = np.ones((2, 2), dtype=np.float32)
    threshold = 0.4
    below = np.full((1, 1), threshold * (1 - 1e-4), dtype=np.float32)
    above = np.full((1, 1), threshold * (1 + 1e-4), dtype=np.float32)
    params = ReconstructionParams(model="ratio", scale=1.0, max_gain_cap=2.0, highlight_threshold=threshold)

    result_below = reconstruct(primary, below, params)
    result_above = reconstruct(primary, above, params)

    relative_change = np.abs(result_above - result_below) / np.maximum(result_below, 1e-6)
    assert np.max(relative_change) < 0.02


def test_zero_threshold_enables_only_strictly_positive_auxiliary():
    primary = np.ones((1, 1), dtype=np.float32)
    params = ReconstructionParams(model="additive-residual", scale=1.0, max_gain_cap=2.0, highlight_threshold=0.0)

    black_result = reconstruct(primary, np.zeros((1, 1), dtype=np.float32), params)
    positive_result = reconstruct(primary, np.ones((1, 1), dtype=np.float32) * 1e-4, params)

    np.testing.assert_array_equal(black_result, primary)
    assert positive_result[0, 0] > primary[0, 0]


def test_unknown_model_is_rejected_instead_of_assuming_vivo_formula():
    with pytest.raises(ValueError):
        reconstruct(np.zeros((1, 1), dtype=np.float32), np.zeros((1, 1), dtype=np.float32), ReconstructionParams(model="unknown", scale=1, max_gain_cap=1, highlight_threshold=0.1))


def test_max_gain_is_a_cap_not_a_direct_standard_gainmap_field():
    primary = np.ones((2, 2), dtype=np.float32)
    auxiliary = np.ones((1, 1), dtype=np.float32)

    result = reconstruct(primary, auxiliary, ReconstructionParams(model="ratio", scale=1.0, max_gain_cap=2.0, highlight_threshold=0.02))

    assert np.max(result / primary) <= 2.0 + 1e-6
