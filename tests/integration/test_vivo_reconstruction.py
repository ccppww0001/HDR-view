from pathlib import Path

import numpy as np
import pytest

from hdrview.vivo.container import inspect_jpeg
from hdrview.vivo.fuse import auxiliary_linear_bt2020, reconstruct_vivo
from hdrview.vivo.reconstruct import ReconstructionParams

SAMPLES = Path(r"D:\MyProject\HDR-view\images\fromthephone")


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="私人原始样本不在工作区")
def test_vivo_reconstruction_preserves_shape_color_and_unknown_xdr_status():
    document = inspect_jpeg(SAMPLES / "IMG_20261116_212648.jpg")

    result = reconstruct_vivo(
        document,
        ReconstructionParams(model="additive-residual", scale=4.0, max_gain_cap=4.5, highlight_threshold=0.02),
    )

    assert result.image.rgba.shape == (3072, 4096, 4)
    assert result.image.color.primaries == "bt2020"
    assert result.image.color.transfer == "linear"
    assert np.all(np.isfinite(result.image.rgba))
    assert np.all(result.image.rgba >= 0)
    assert result.xdr_appearance_verified is False
    assert result.image.provenance["source_sha256"] == document.sha256
    assert "未验证" in result.diagnostics["status"]


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="私人原始样本不在工作区")
def test_auxiliary_p3_is_not_clipped_to_srgb_before_linearization():
    document = inspect_jpeg(SAMPLES / "IMG_20261116_212648.jpg")
    from hdrview.vivo.auxiliary import extract_auxiliary_jpeg

    result = auxiliary_linear_bt2020(extract_auxiliary_jpeg(document), (64, 48))

    assert result.shape == (48, 64, 3)
    assert np.all(np.isfinite(result))
    # 夜景黑色像素保持为零；色彩变换由独立合成色板测试验证。
    assert float(np.min(result)) == 0


def test_black_auxiliary_returns_original_linear_sdr():
    primary = np.array([[0.0, 0.1], [0.4, 0.8]], dtype=np.float32)
    auxiliary = np.zeros((2, 2), dtype=np.float32)
    from hdrview.vivo.reconstruct import reconstruct

    result = reconstruct(primary, auxiliary, ReconstructionParams("ratio", 4.0, 4.5, 0.02))

    np.testing.assert_array_equal(result, primary)
    assert not np.any(np.isnan(result))
