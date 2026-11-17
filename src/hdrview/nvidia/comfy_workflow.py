"""生成显式连接的 ComfyUI 工作流；Ultra HDR 不在核心节点中伪造。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrueHdrParams:
    contrast: int = 100
    saturation: int = 100
    middle_gray: int = 50
    luminance: int = 400
    debanding: bool = True
    output_colorspace: str = "HDR PQ"

    def validate(self) -> None:
        if self.output_colorspace != "HDR PQ":
            raise ValueError("本项目 NVIDIA 工作流固定使用 BT.2020/PQ，不使用 HLG 默认路径")
        if not 400 <= self.luminance <= 2000:
            raise ValueError("TrueHDR luminance 必须在 400–2000 nit")
        if not (0 <= self.contrast <= 200 and 0 <= self.saturation <= 200 and 10 <= self.middle_gray <= 100):
            raise ValueError("TrueHDR 对比/饱和/中灰超出官方范围")


def build_workflow(input_png: Path, params: TrueHdrParams, *, output_stem: Path, source_sha256: str) -> dict:
    """节点 ID 稳定，真实链路不能靠未连接的文件说明替代。"""

    params.validate()
    if len(source_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in source_sha256):
        raise ValueError("工作流必须携带原始图片的 SHA-256")
    if not output_stem.name:
        raise ValueError("必须提供 HDR 中间结果的输出 stem")
    return {
        "nodes": [
            {"id": 1, "type": "LoadImage", "widgets_values": [input_png.name, "image"]},
            {"id": 2, "type": "HdrViewPrepareTrueHDR", "inputs": [{"name": "images", "type": "IMAGE", "link": 1}], "widgets_values": []},
            {"id": 3, "type": "RTXTrueHDR", "inputs": [{"name": "images", "type": "IMAGE", "link": 2}], "widgets_values": [params.contrast, params.saturation, params.middle_gray, params.luminance, params.debanding, params.output_colorspace]},
            {"id": 4, "type": "HdrViewSaveLinear", "inputs": [{"name": "images", "type": "IMAGE", "link": 3}], "widgets_values": [str(output_stem), source_sha256, params.luminance]},
        ],
        "links": [[1, 1, 0, 2, 0, "IMAGE"], [2, 2, 0, 3, 0, "IMAGE"], [3, 3, 0, 4, 0, "IMAGE"]],
    }
