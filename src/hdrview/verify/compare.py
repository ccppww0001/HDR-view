"""对重建与 SDR 的几何、亮度、颜色证据生成机器可读摘要。"""

from __future__ import annotations

import numpy as np

from hdrview.model import HdrImage, SdrImage
from hdrview.color.gamut import rec709_to_bt2020
from hdrview.color.transfer import srgb_to_linear


def compare_reconstruction(hdr: HdrImage, sdr: SdrImage) -> dict[str, float | bool | str]:
    """检查增强范围，不用“全图更亮”作为质量标准。"""

    base = rec709_to_bt2020(srgb_to_linear(sdr.rgba[..., :3].astype(np.float32) / 255))
    hdr_rgb = hdr.rgba[..., :3]
    ratio = hdr_rgb / np.maximum(base, 1e-8)
    changed = np.max(np.abs(hdr_rgb - base), axis=2) > 1e-5
    return {
        "source_sha256": str(hdr.provenance.get("source_sha256", "")),
        "changed_fraction": float(np.mean(changed)),
        "maximum_ratio": float(np.max(ratio)),
        "hdr_capacity_max": hdr.hdr_capacity_max,
        "xdr_appearance_verified": False,
        "status": "合理 HDR 重建，手机 XDR 观感未验证",
    }
