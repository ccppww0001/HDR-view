"""float16 RGBA + JSON 的可校验 HDR 中间格式。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from hdrview.errors import InvalidIntermediateError
from hdrview.model import ColorState, HdrImage


@dataclass(frozen=True)
class IntermediatePaths:
    stem: Path
    pixel: Path
    metadata: Path


def _paths(stem: Path) -> IntermediatePaths:
    return IntermediatePaths(stem=stem, pixel=stem.with_suffix(".f16rgba"), metadata=stem.with_suffix(".json"))


def _validate(image: HdrImage) -> tuple[int, int, np.ndarray]:
    rgba = np.asarray(image.rgba, dtype=np.float32)
    if image.color.primaries != "bt2020" or image.color.transfer != "linear":
        raise InvalidIntermediateError("中间 HDR 必须为 BT.2020 linear")
    if rgba.ndim != 3 or rgba.shape[2] != 4 or rgba.shape[0] < 1 or rgba.shape[1] < 1:
        raise InvalidIntermediateError("HDR 像素必须是非空 H×W×4 RGBA")
    if not np.all(np.isfinite(rgba)) or np.any(rgba < 0) or np.any(rgba > 65504):
        raise InvalidIntermediateError("HDR 像素必须有限、非负且不超过 float16 上限 65504")
    if not np.array_equal(rgba[..., 3], np.ones(rgba.shape[:2], dtype=np.float32)):
        raise InvalidIntermediateError("照片中间表示仅支持 alpha=1")
    if not np.isfinite(image.hdr_capacity_max) or image.hdr_capacity_max < 1:
        raise InvalidIntermediateError("hdr_capacity_max 必须是有限且不小于 1 的倍率")
    if image.color.sdr_white_nits != 203.0:
        raise InvalidIntermediateError("中间格式固定 SDR 参考白为 203 nit")
    source_hash = image.provenance.get("source_sha256")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        raise InvalidIntermediateError("缺少有效的源图 SHA-256")
    return rgba.shape[0], rgba.shape[1], rgba


def write_intermediate(image: HdrImage, stem: Path) -> IntermediatePaths:
    """先完整校验，再写新像素与 JSON；不自动覆盖已有中间文件。"""

    height, width, rgba = _validate(image)
    paths = _paths(stem)
    if paths.pixel.exists() or paths.metadata.exists():
        raise InvalidIntermediateError("中间输出已存在，拒绝覆盖")
    paths.stem.parent.mkdir(parents=True, exist_ok=True)
    rgba.astype(np.float16).tofile(paths.pixel)
    payload = {
        "schema": 1,
        "width": width,
        "height": height,
        "channels": 4,
        "pixel_format": "rgba-float16",
        "byte_stride": width * 8,
        "primaries": "bt2020",
        "transfer": "linear",
        "sdr_white_nits": 203.0,
        "hdr_capacity_max": image.hdr_capacity_max,
        "provenance": image.provenance,
    }
    paths.metadata.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return paths


def read_intermediate(stem: Path) -> HdrImage:
    """sidecar 是像素解释的必要条件，不根据扩展名推断 HDR。"""

    paths = _paths(stem)
    try:
        payload = json.loads(paths.metadata.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidIntermediateError("中间 sidecar 缺失或损坏") from error
    expected = {
        "schema": 1,
        "channels": 4,
        "pixel_format": "rgba-float16",
        "primaries": "bt2020",
        "transfer": "linear",
        "sdr_white_nits": 203.0,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise InvalidIntermediateError("中间 sidecar 格式或色彩空间不匹配")
    width, height = payload.get("width"), payload.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1:
        raise InvalidIntermediateError("中间图尺寸无效")
    if width > 16384 or height > 16384 or payload.get("byte_stride") != width * 8:
        raise InvalidIntermediateError("中间图尺寸/stride 超出限制")
    raw = paths.pixel.read_bytes()
    if len(raw) != width * height * 8:
        raise InvalidIntermediateError("中间像素字节数与 sidecar 不匹配")
    rgba = np.frombuffer(raw, dtype="<f2").reshape(height, width, 4).astype(np.float32)
    capacity = payload.get("hdr_capacity_max")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise InvalidIntermediateError("中间 provenance 缺失")
    image = HdrImage(
        rgba=rgba,
        color=ColorState(primaries="bt2020", transfer="linear"),
        hdr_capacity_max=capacity,
        provenance=provenance,
    )
    _validate(image)
    return image
