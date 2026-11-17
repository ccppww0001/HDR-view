"""候选重建模型仅用于研究；每个模型都显式标记其未经证实的假设。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np


@dataclass(frozen=True)
class ReconstructionParams:
    model: Literal["additive-residual", "ratio", "short-exposure"]
    scale: float
    max_gain_cap: float
    highlight_threshold: float


def _validate(primary: np.ndarray, auxiliary: np.ndarray, params: ReconstructionParams) -> None:
    if primary.ndim != 2 or auxiliary.ndim != 2 or primary.size == 0 or auxiliary.size == 0:
        raise ValueError("候选模型要求非空二维亮度输入")
    if not np.all(np.isfinite(primary)) or not np.all(np.isfinite(auxiliary)):
        raise ValueError("候选模型输入必须有限")
    if np.any(primary < 0) or np.any(auxiliary < 0):
        raise ValueError("亮度输入必须非负")
    if params.scale < 0 or params.max_gain_cap < 1 or not 0 <= params.highlight_threshold <= 1:
        raise ValueError("重建参数超出安全范围")


def reconstruct(primary: np.ndarray, auxiliary: np.ndarray, params: ReconstructionParams) -> np.ndarray:
    """高光区域内做受限候选变换；纯黑辅助图不改变主图。"""

    _validate(primary, auxiliary, params)
    auxiliary_full = cv2.resize(auxiliary, (primary.shape[1], primary.shape[0]), interpolation=cv2.INTER_LINEAR)
    mask = auxiliary_full > params.highlight_threshold
    result = primary.copy()
    if params.model == "additive-residual":
        candidate = primary + params.scale * auxiliary_full
        result[mask] = np.minimum(candidate[mask], primary[mask] * params.max_gain_cap)
    elif params.model == "ratio":
        # 辅助亮度只映射到 1..maxGain 的候选比值；不是已证实的 vivo 公式。
        candidate = primary * (1 + (params.max_gain_cap - 1) * auxiliary_full * params.scale)
        result[mask] = np.minimum(candidate[mask], primary[mask] * params.max_gain_cap)
    elif params.model == "short-exposure":
        # 作为曝光辅助假设的诊断：以受限高光增强近似，不宣称恢复了真实原始曝光。
        candidate = primary * (1 + auxiliary_full * params.scale)
        result[mask] = np.minimum(candidate[mask], primary[mask] * params.max_gain_cap)
    else:
        raise ValueError(f"未知候选重建模型：{params.model}")
    if not np.all(np.isfinite(result)):
        raise ValueError("候选重建产生非有限值")
    return result
