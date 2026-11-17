"""NVIDIA Python API 输入契约：Rec.709/D65 gamma 2.2。"""

from __future__ import annotations

import numpy as np

from hdrview.color.transfer import srgb_to_rec709_gamma22
from hdrview.model import SdrImage


def prepare_truehdr_input(sdr: SdrImage) -> np.ndarray:
    """只接受 RGBA8 的 sRGB 解码结果，显式转换传递函数。"""

    rgba = np.asarray(sdr.rgba)
    if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.dtype != np.uint8:
        raise ValueError("TrueHDR 预处理需要 RGBA8 sRGB 输入")
    return srgb_to_rec709_gamma22(rgba[..., :3].astype(np.float32) / 255)
