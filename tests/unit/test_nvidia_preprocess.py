from __future__ import annotations

import numpy as np
import pytest

from hdrview.model import SdrImage
from hdrview.nvidia.preprocess import prepare_truehdr_input


def test_truehdr_input_is_rec709_gamma22_not_srgb_passthrough():
    rgba = np.zeros((1, 2, 4), dtype=np.uint8)
    rgba[0, 0, :3] = [13, 26, 51]
    rgba[..., 3] = 255
    sdr = SdrImage(rgba, None, None)

    result = prepare_truehdr_input(sdr)

    assert result.dtype == np.float32
    assert result.shape == (1, 2, 3)
    np.testing.assert_allclose(
        result[0, 0],
        [((value / 255 + 0.055) / 1.055) ** (2.4 / 2.2) for value in (13, 26, 51)],
        rtol=1e-6,
    )
    assert not np.array_equal(result, rgba[..., :3].astype(np.float32) / 255)


def test_truehdr_input_rejects_alpha_or_wrong_shape():
    with pytest.raises(ValueError):
        prepare_truehdr_input(SdrImage(np.zeros((2, 2, 3), dtype=np.uint8), None, None))
