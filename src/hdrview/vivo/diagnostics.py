"""主辅图几何、亮度和覆盖范围的诊断，不推断 vivo 私有算法。"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path

import cv2
import numpy as np

from hdrview.color.icc import decode_with_icc
from hdrview.vivo.auxiliary import extract_auxiliary_jpeg
from hdrview.vivo.container import inspect_jpeg


@dataclass(frozen=True)
class AlignmentReport:
    primary_size: tuple[int, int]
    auxiliary_size: tuple[int, int]
    auxiliary_nonzero_fraction: float
    auxiliary_luminance_max: float
    highlight_center: tuple[float, float] | None
    highlight_bbox: tuple[int, int, int, int] | None
    correlation_with_primary_highlights: float | None
    highlight_overlap_fraction: float
    primary_highlight_fraction: float


def _luma(rgb: np.ndarray) -> np.ndarray:
    return np.einsum("...c,c->...", rgb, np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))


def analyze_vivo_alignment(primary: np.ndarray, auxiliary: np.ndarray) -> AlignmentReport:
    """统一在 sRGB 数值域比较亮度位置；不将此相关性称为光强公式。"""

    if primary.ndim == 3:
        primary_luma = _luma(primary)
    else:
        primary_luma = np.asarray(primary, dtype=np.float32)
    if auxiliary.ndim == 3:
        auxiliary_luma = _luma(auxiliary)
    else:
        auxiliary_luma = np.asarray(auxiliary, dtype=np.float32)
    if primary_luma.ndim != 2 or auxiliary_luma.ndim != 2 or primary_luma.size == 0 or auxiliary_luma.size == 0:
        raise ValueError("主辅诊断需要非空二维亮度或 RGB 图像")
    if not np.all(np.isfinite(primary_luma)) or not np.all(np.isfinite(auxiliary_luma)):
        raise ValueError("亮度图必须有限")
    threshold = 8 / 255
    mask = auxiliary_luma > threshold
    ys, xs = np.nonzero(mask)
    center = None
    bbox = None
    if len(xs):
        center = (float(xs.mean()), float(ys.mean()))
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    resized = cv2.resize(auxiliary_luma, (primary_luma.shape[1], primary_luma.shape[0]), interpolation=cv2.INTER_LINEAR)
    bright = resized > threshold
    primary_bright = primary_luma > np.quantile(primary_luma, 0.95)
    overlap = float(np.mean(primary_bright[bright])) if np.any(bright) else 0.0
    correlation = None
    # 常亮区域只做位置/覆盖诊断，不对常数数组计算无意义相关系数。
    if np.count_nonzero(bright) > 2 and float(np.std(resized[bright], dtype=np.float64)) > 1e-12 and float(np.std(primary_luma[bright], dtype=np.float64)) > 1e-12:
        correlation = float(np.corrcoef(resized[bright], primary_luma[bright])[0, 1])
    return AlignmentReport(
        primary_size=(primary_luma.shape[1], primary_luma.shape[0]),
        auxiliary_size=(auxiliary_luma.shape[1], auxiliary_luma.shape[0]),
        auxiliary_nonzero_fraction=float(np.mean(mask)),
        auxiliary_luminance_max=float(np.max(auxiliary_luma)),
        highlight_center=center,
        highlight_bbox=bbox,
        correlation_with_primary_highlights=correlation,
        highlight_overlap_fraction=overlap,
        primary_highlight_fraction=float(np.mean(primary_bright)),
    )


def analyze_file(path: Path) -> dict:
    """读取真实文件的 ICC 正确主辅图，并输出可序列化证据。"""

    document = inspect_jpeg(path)
    if document.vivo is None:
        raise ValueError("输入不含 vivo 私有辅助图")
    primary_jpeg = document.data[: document.vivo.primary_eoi_offset + 2]
    primary = decode_with_icc(primary_jpeg).rgba[..., :3].astype(np.float32) / 255
    auxiliary = decode_with_icc(extract_auxiliary_jpeg(document)).rgba[..., :3].astype(np.float32) / 255
    report = analyze_vivo_alignment(primary, auxiliary)
    return {"source_sha256": document.sha256, **asdict(report)}
