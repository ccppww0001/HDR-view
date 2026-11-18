# 上游与参考来源

## Luma HDR Photo Viewer

参考 Luma 的 `GainMap.h` 和 `Luma.Native.cpp`，用于理解增益图映射、scRGB 及 80 尼特参考白。选用的源码快照对应 Luma 0.1.32，采用 MIT 许可证。[Luma 源码提交](https://github.com/lueluelue12138/luma-hdr-photo-viewer/commit/881361c2a3002cd8bdefa4922fc8ae18eb2d0a28)

Luma 也用作本地显示参考，已在既有样本验收中识别同时写入 ISO 21496-1 和 XMP 的 Ultra HDR JPEG。[验证记录](../verification.md)

## Comfy-Org NVIDIA VFX Nodes

参考节点中的 `nvvfx.TrueHDR` 调用、Rec.709 gamma 2.2 输入约定，以及 BT.2020/PQ 输出的 RGB10A2 位解包。参考快照对应节点软件 0.2.1，采用 Apache 2.0 许可证。HDR-view 的模型调用和输出转换位于 `src/hdrview/nvidia/runtime.py`。[节点源码提交](https://github.com/Comfy-Org/ComfyUI_Nvidia_VFX_Nodes/commit/38d790ded00650681fa3645362efe28c8560cf40)

## NVIDIA 官方模型

运行时直接调用 NVIDIA 视频效果软件包提供的 `TrueHDR` 和 `VideoSuperRes`。独立环境 `.venv-nvidia` 使用包含 TrueHDR 的 NVIDIA 视频效果软件包 0.2.0.0，以及 PyTorch 2.11.0 的 CUDA 12.8 构建。[NVIDIA Python 接口](https://docs.nvidia.com/maxine/vfx-python/latest/api.html) · [环境配置](../workflows/nvidia-truehdr.md#安装环境)

在 NVIDIA GeForce RTX 4070 Laptop 显卡和 617.14 驱动上处理过真实夜景样本。官方默认计算流 `stream_ptr=0` 用于模型运行。RGB10A2 输出先复制到主机，再由 NumPy 解包。报告分别记录模型的 `luminance` 参数与内容容量，历史样张和接口测试的证据见[验证记录](../verification.md)。

## 编码组件

- Google libultrahdr 2.0.2 提供 Ultra HDR 的编码、结构检查和参考解码接口。[Google libultrahdr 源码](https://github.com/google/libultrahdr/tree/e5f5a022fe96fc4dc2ee35c19f733a50df807abe)
- libjpeg-turbo 3.2.0 提供 JPEG 编解码，由原生构建脚本以固定源码构建。[libjpeg-turbo 源码](https://github.com/libjpeg-turbo/libjpeg-turbo/tree/3.2.0)
- Windows Imaging Component 提供浮点 JPEG XR 编解码。构建来源、校验值和颜色变换见[原生组件说明](../../src/hdrview/native/README.md)与[色彩流程](color-pipeline.md)。
