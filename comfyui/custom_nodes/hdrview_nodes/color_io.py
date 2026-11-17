"""最小 ComfyUI 色彩输入和 PQ 中间保存节点。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from hdrview.color.transfer import pq_to_linear_bt2020
from hdrview.io.intermediate import write_intermediate
from hdrview.model import ColorState, HdrImage
from hdrview.nvidia.preprocess import prepare_truehdr_input
from hdrview.model import SdrImage

try:
    from comfy_api.latest import io
except ImportError:  # 单元测试不伪造 ComfyUI 运行成功。
    io = None


if io is not None:
    class HdrViewPrepareTrueHDR(io.ComfyNode):
        @classmethod
        def define_schema(cls):
            return io.Schema(
                node_id="HdrViewPrepareTrueHDR",
                display_name="HDR-view：Rec.709 gamma 2.2 输入",
                category="image/hdrview",
                inputs=[io.Image.Input("images")],
                outputs=[io.Image.Output("prepared_images")],
            )

        @classmethod
        def execute(cls, images):
            values = images.detach().to(device="cpu", dtype=torch.float32).numpy()
            output = np.stack([prepare_truehdr_input(SdrImage(
                np.concatenate([np.rint(frame * 255).astype(np.uint8), np.full((*frame.shape[:2], 1), 255, dtype=np.uint8)], axis=-1),
                None,
                None,
            )) for frame in values])
            return io.NodeOutput(torch.from_numpy(output).to(device=images.device))


    class HdrViewSaveLinear(io.ComfyNode):
        @classmethod
        def define_schema(cls):
            return io.Schema(
                node_id="HdrViewSaveLinear",
                display_name="HDR-view：保存线性 HDR 中间结果",
                category="image/hdrview",
                is_output_node=True,
                inputs=[
                    io.Image.Input("images"),
                    io.String.Input("output_stem"),
                    io.String.Input("source_sha256"),
                    io.Int.Input("luminance", default=400, min=400, max=2000),
                ],
                outputs=[],
            )

        @classmethod
        def execute(cls, images, output_stem, source_sha256, luminance):
            for index, image in enumerate(images):
                # 官方 RTXTrueHDR 返回归一化 PQ 数值；转为绝对亮度再归一到 203 nit。
                pq = image.detach().to(device="cpu", dtype=torch.float32).numpy()[..., :3]
                linear = pq_to_linear_bt2020(pq) / 203.0
                rgba = np.concatenate([linear, np.ones((*linear.shape[:2], 1), dtype=np.float32)], axis=-1)
                hdr = HdrImage(
                    rgba=rgba,
                    color=ColorState("bt2020", "linear"),
                    hdr_capacity_max=float(luminance / 203.0),
                    provenance={"source_sha256": source_sha256, "pipeline": "nvidia-truehdr", "luminance": luminance},
                )
                stem = Path(output_stem)
                if index:
                    stem = stem.with_name(stem.name + f"-{index:03d}")
                write_intermediate(hdr, stem)
            return None
