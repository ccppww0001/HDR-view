"""Rec.709 与 BT.2020 色度转换；传递函数在独立模块处理。"""

from __future__ import annotations

import numpy as np

REC709_TO_BT2020 = np.array(
    [
        [0.6274038959, 0.3292830384, 0.0433130657],
        [0.0690972894, 0.9195403951, 0.0113623155],
        [0.0163914389, 0.0880133079, 0.8955952532],
    ],
    dtype=np.float32,
)


def rec709_to_bt2020(rgb: np.ndarray) -> np.ndarray:
    """输入/输出均为线性光，非负约束由 HdrImage 边界验证。"""

    return np.einsum("...c,dc->...d", np.asarray(rgb, dtype=np.float32), REC709_TO_BT2020).astype(np.float32)
