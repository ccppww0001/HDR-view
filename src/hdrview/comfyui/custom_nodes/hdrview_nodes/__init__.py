"""HDR-view 的薄 ComfyUI 节点；不重新实现 NVIDIA 滤镜或 Ultra HDR 容器。"""

from .color_io import HdrViewPrepareTrueHDR, HdrViewSaveLinear


class HdrViewComfyExtension:
    async def get_node_list(self):
        return [HdrViewPrepareTrueHDR, HdrViewSaveLinear]


async def comfy_entrypoint():
    return HdrViewComfyExtension()


# 供旧式扫描器识别；当前 ComfyUI 通过 comfy_entrypoint 使用同一批类。
NODE_CLASS_MAPPINGS = {
    "HdrViewPrepareTrueHDR": HdrViewPrepareTrueHDR,
    "HdrViewSaveLinear": HdrViewSaveLinear,
}
