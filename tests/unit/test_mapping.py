from __future__ import annotations

import numpy as np
import pytest

from hdrview.mapping import DisplayMapping, map_highlights
from hdrview.model import ColorState, HdrImage


def make_hdr(rgb: list[list[float]], capacity: float = 5.0) -> HdrImage:
    rgba = np.ones((len(rgb), 1, 4), dtype=np.float32)
    rgba[:, 0, :3] = np.asarray(rgb, dtype=np.float32)
    return HdrImage(
        rgba=rgba,
        color=ColorState(primaries="bt2020", transfer="linear"),
        hdr_capacity_max=capacity,
        provenance={"source_sha256": "a" * 64, "display_mapping": "none"},
    )


def test_sdr_and_black_pixels_are_unchanged_and_provenance_is_augmented():
    image = make_hdr([[0.0, 0.0, 0.0], [0.1, 0.2, 0.3], [1.0, 0.5, 0.2]])

    result = map_highlights(image, DisplayMapping())

    np.testing.assert_array_equal(result.rgba, image.rgba)
    assert result.color == image.color
    assert result.hdr_capacity_max == image.hdr_capacity_max
    assert result.provenance["source_sha256"] == "a" * 64
    assert result.provenance["display_mapping"] == "hdr400-highlight-compression"
    assert result.provenance["target_nits"] == 400
    assert result.provenance["knee_ratio"] == pytest.approx(0.8)
    assert image.provenance["display_mapping"] == "none"


def test_hdr400_mapping_is_strictly_ordered_continuous_and_bounded():
    knee = 1 + (400 / 203 - 1) * 0.8
    luminances = np.array([1.001, 1.2, 1.4, 1.5, knee - 0.001, knee, knee + 0.001, 1.8, 2.5, 10.0, 1000.0], dtype=np.float64)
    # BT.2020 亮度权重之和为 1；等 RGB 可避免 float32 构造样本时偏离目标亮度。
    rgb = np.repeat(luminances[:, None], 3, axis=1)
    image = make_hdr(rgb.tolist(), capacity=65504.0)

    result = map_highlights(image, DisplayMapping())
    mapped = np.asarray(result.rgba[:, 0, :3], dtype=np.float64)
    mapped_luminance = mapped @ np.array([0.2627, 0.6780, 0.0593])

    assert np.all(np.isfinite(result.rgba))
    assert np.all(np.diff(mapped_luminance) > 0)
    assert np.max(mapped_luminance) <= 400 / 203 + 1e-6
    knee_index = int(np.where(luminances == knee)[0][0])
    assert mapped_luminance[knee_index] == pytest.approx(knee, rel=1e-6)
    # 检查相邻采样没有产生亮度阶跃或改变原始 RGB 比例。
    assert np.max(np.abs(np.diff(mapped_luminance[knee_index - 1:knee_index + 2]))) < 0.01
    np.testing.assert_allclose(mapped / mapped[:, :1], rgb / rgb[:, :1], rtol=1e-6)


def test_hdr400_mapping_has_matching_one_sided_derivatives_at_knee():
    knee = 1 + (400 / 203 - 1) * 0.8
    step = 0.001
    luminances = np.array([knee - 2 * step, knee - step, knee, knee + step, knee + 2 * step], dtype=np.float64)
    image = make_hdr(np.repeat(luminances[:, None], 3, axis=1).tolist(), capacity=65504.0)

    result = map_highlights(image, DisplayMapping())
    mapped_luminance = np.asarray(result.rgba[:, 0, :3], dtype=np.float64) @ np.array([0.2627, 0.6780, 0.0593])
    left_derivative = (mapped_luminance[1] - mapped_luminance[0]) / step
    right_derivative = (mapped_luminance[4] - mapped_luminance[3]) / step

    # float32 像素输出及 0.001 步长会带来少量有限差分量化误差。
    assert left_derivative == pytest.approx(right_derivative, rel=0.05)


def test_high_intensity_input_remains_finite_without_silent_peak_clipping():
    image = make_hdr([[10000.0, 10000.0, 10000.0]], capacity=65504.0)

    result = map_highlights(image, DisplayMapping())
    luminance = np.asarray(result.rgba[0, 0, :3], dtype=np.float64) @ np.array([0.2627, 0.6780, 0.0593])

    assert np.all(np.isfinite(result.rgba))
    assert 1.595 < luminance < 400 / 203


def test_nearby_highlights_keep_distinct_luminance_levels():
    image = make_hdr([[1.8, 1.8, 1.8], [1.8001, 1.8001, 1.8001]], capacity=5.0)

    result = map_highlights(image, DisplayMapping())

    assert result.rgba[1, 0, 0] > result.rgba[0, 0, 0]


def test_invalid_mapping_parameters_are_rejected():
    image = make_hdr([[0.0, 0.0, 0.0]])
    for params in (DisplayMapping(peak_nits=202), DisplayMapping(peak_nits=400, knee_ratio=0.0), DisplayMapping(peak_nits=400, knee_ratio=1.0)):
        with pytest.raises(ValueError):
            map_highlights(image, params)
