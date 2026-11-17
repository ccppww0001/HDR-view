"""ComfyUI TrueHDR 已保存中间结果的输入一致性检查。"""

from __future__ import annotations

from pathlib import Path

from hdrview.io.intermediate import read_intermediate
from hdrview.model import HdrImage


def read_truehdr_output(stem: Path, *, expected_source_sha256: str | None = None) -> HdrImage:
    """中间结果必须绑定原图，不允许把其它照片的 HDR 套到当前 SDR。"""

    image = read_intermediate(stem)
    if image.provenance.get("pipeline") != "nvidia-truehdr":
        raise ValueError("中间结果不是已声明的 NVIDIA TrueHDR 管线")
    if expected_source_sha256 and image.provenance.get("source_sha256") != expected_source_sha256:
        raise ValueError("中间结果与原始照片的 SHA-256 不匹配")
    return image
