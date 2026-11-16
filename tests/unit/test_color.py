from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageCms

from hdrview.color.gamut import rec709_to_bt2020
from hdrview.color.icc import decode_with_icc
from hdrview.color.transfer import (
    linear_to_srgb,
    pq_to_linear_bt2020,
    srgb_to_linear,
    srgb_to_rec709_gamma22,
)


def test_srgb_piecewise_reference_points():
    values = np.array([0.0, 0.04045, 0.5, 1.0], dtype=np.float32)
    linear = srgb_to_linear(values)

    np.testing.assert_allclose(linear, [0.0, 0.04045 / 12.92, 0.21404114, 1.0], rtol=1e-6)
    np.testing.assert_allclose(linear_to_srgb(linear), values, atol=1e-7)


def test_rec709_gamma22_differs_from_srgb_in_dark_values():
    encoded = np.array([0.02, 0.04045, 0.5], dtype=np.float32)
    expected = np.power(np.array([0.02 / 12.92, 0.04045 / 12.92, 0.21404114], dtype=np.float32), 1.0 / 2.2)

    np.testing.assert_allclose(srgb_to_rec709_gamma22(encoded), expected, rtol=1e-7)
    assert not np.allclose(srgb_to_rec709_gamma22(encoded), encoded)


@pytest.mark.parametrize(
    "nits,encoded",
    [(0.0, 0.0), (100.0, 0.5080784), (203.0, 0.5806892), (1000.0, 0.7518271), (10000.0, 1.0)],
)
def test_pq_reference_luminance(nits: float, encoded: float):
    actual = pq_to_linear_bt2020(np.array([encoded], dtype=np.float32))

    assert actual[0] == pytest.approx(nits, rel=2e-4, abs=1e-5)


def test_rec709_to_bt2020_white_stays_neutral():
    rgb = np.array([1.0, 1.0, 1.0], dtype=np.float32)

    actual = rec709_to_bt2020(rgb)

    np.testing.assert_allclose(actual, [1.0, 1.0, 1.0], atol=1e-6)


def test_rec709_pure_red_expands_into_bt2020():
    actual = rec709_to_bt2020(np.array([1.0, 0.0, 0.0], dtype=np.float32))

    np.testing.assert_allclose(actual, [0.6274039, 0.0690973, 0.0163914], atol=1e-6)


def test_decode_uses_display_p3_icc_instead_of_discarding_it():
    source = Path(r"D:\MyProject\HDR-view\images\fromthephone\IMG_20261116_212648.jpg")
    if not source.is_file():
        pytest.skip("真实 Display-P3 配置不在本机")
    with Image.open(source) as phone:
        p3_icc = phone.info["icc_profile"]
    image = Image.new("RGB", (2, 1))
    image.putdata([(200, 30, 30), (0, 128, 255)])
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=100, subsampling=0, icc_profile=p3_icc)

    decoded = decode_with_icc(buffer.getvalue())

    assert decoded.rgba.shape == (1, 2, 4)
    # P3 纯红进入较小的 sRGB 色域后必须改变通道，不得原样透传。
    assert decoded.rgba[0, 0, 0] > 200
    assert decoded.rgba[0, 0, 1] < 30
    assert decoded.icc is not None
    assert "srgb" in ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(BytesIO(decoded.icc))).lower()


def test_decode_rejects_invalid_jpeg():
    with pytest.raises((OSError, ValueError)):
        decode_with_icc(b"not-jpeg")
