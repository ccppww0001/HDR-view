"""共享 HDR 高光映射：仅压缩目标显示范围外的亮度，不改变色域或原图。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from hdrview.io.intermediate import _validate
from hdrview.model import HdrImage


@dataclass(frozen=True)
class DisplayMapping:
    """以 203 nit 线性 BT.2020 中间表示为输入的显示映射参数。"""

    peak_nits: int = 400
    knee_ratio: float = 0.8


def map_highlights(hdr: HdrImage, params: DisplayMapping) -> HdrImage:
    """按 BT.2020 亮度比例压缩高光，保持 SDR 像素、RGB 比例及 alpha 不变。"""

    _, _, rgba = _validate(hdr)
    if (
        not isinstance(params.peak_nits, int)
        or isinstance(params.peak_nits, bool)
        or params.peak_nits <= 203
        or not np.isfinite(params.knee_ratio)
        or not 0 < params.knee_ratio < 1
    ):
        raise ValueError("显示映射要求峰值大于 203 nit 且拐点比例在 0 与 1 之间")

    peak = params.peak_nits / 203.0
    knee = 1.0 + (peak - 1.0) * params.knee_ratio
    tail = peak - knee
    luminance = np.sum(rgba[..., :3].astype(np.float64) * np.array([0.2627, 0.6780, 0.0593]), axis=2)
    mapped = luminance.copy()

    low = (luminance > 1.0) & (luminance <= knee)
    # 端点值、两端斜率为 1 与单调上限共同决定低亮段为恒等映射。
    mapped[low] = luminance[low]
    high = luminance > knee
    x_high = (luminance[high] - knee) / tail
    mapped[high] = knee + tail * x_high / (1.0 + x_high)

    result = rgba.copy()
    hdr_pixels = luminance > 1.0
    # 仅处理大于 SDR 参考白的亮度，不静默裁剪超高峰值或极小负 RGB 分量。
    scale = np.ones_like(luminance)
    scale[hdr_pixels] = mapped[hdr_pixels] / luminance[hdr_pixels]
    result[..., :3] = (result[..., :3].astype(np.float64) * scale[..., None]).astype(np.float32)
    provenance = dict(hdr.provenance)
    provenance.update(
        display_mapping="hdr400-highlight-compression",
        target_nits=params.peak_nits,
        knee_ratio=params.knee_ratio,
    )
    return HdrImage(rgba=result, color=hdr.color, hdr_capacity_max=hdr.hdr_capacity_max, provenance=provenance)
