"""sRGB、Rec.709 gamma 2.2 与 SMPTE ST 2084 PQ 的明确转换。"""

from __future__ import annotations

import numpy as np


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    """将 sRGB 电信号转为线性光，保持 float32 与输入形状。"""

    values = np.asarray(rgb, dtype=np.float32)
    if not np.all(np.isfinite(values)):
        raise ValueError("sRGB 输入必须有限")
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    """将非负线性光编码为 sRGB；调用者负责色域映射。"""

    values = np.asarray(rgb, dtype=np.float32)
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("线性光必须有限且非负")
    return np.where(values <= 0.0031308, values * 12.92, 1.055 * values ** (1 / 2.4) - 0.055).astype(np.float32)


def srgb_to_rec709_gamma22(rgb: np.ndarray) -> np.ndarray:
    """先移除 sRGB 曲线，再施加 NVIDIA 所需的 Rec.709 gamma 2.2。"""

    return srgb_to_linear(rgb) ** (1.0 / 2.2)


def pq_to_linear_bt2020(rgb: np.ndarray, *, peak_nits: float = 10000.0) -> np.ndarray:
    """PQ 编码转为显示参考绝对亮度（nit），不把它误称场景线性。"""

    if not math_is_finite_positive(peak_nits) or peak_nits > 10000:
        raise ValueError("PQ 参考峰值必须在 (0,10000] nit")
    encoded = np.asarray(rgb, dtype=np.float32)
    if not np.all(np.isfinite(encoded)) or np.any((encoded < 0) | (encoded > 1)):
        raise ValueError("PQ 输入必须是有限的 [0,1] 数值")
    m1 = 2610 / 16384
    m2 = 2523 / 32
    c1 = 3424 / 4096
    c2 = 2413 / 128
    c3 = 2392 / 128
    power = encoded ** (1 / m2)
    linear = ((np.maximum(power - c1, 0)) / np.maximum(c2 - c3 * power, 1e-12)) ** (1 / m1)
    return (linear * peak_nits).astype(np.float32)


def math_is_finite_positive(value: float) -> bool:
    return bool(np.isfinite(value) and value > 0)
