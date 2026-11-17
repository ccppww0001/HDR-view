# 上游源码与当前实现边界

## Luma HDR Photo Viewer

固定版本 `v0.1.32`，提交 `881361c2a3002cd8bdefa4922fc8ae18eb2d0a28`，MIT 许可。本项目只读参考其 `GainMap.h`、`Luma.Native.cpp` 的增益映射与 scRGB/80 尼特解释，不复制查看器。Luma 源码直接调用官方 NGX TrueHDR 和 VSR，主程序不提供图像导出 API，只作为本地 HDR 显示对照。

NVIDIA SDK、模型和运行库存在闭源边界；Luma 的构建不是完全可复现证明。既有用户验收中 Luma 能识别双写 ISO/XMP 的 Ultra HDR；本次未进行桌面或显示验证。

## Comfy-Org NVIDIA VFX Nodes（只读参考）

固定提交 `38d790ded00650681fa3645362efe28c8560cf40`，Apache-2.0 许可，仓库节点版本 0.2.1。仅参考官方 `nvvfx.TrueHDR` 调用、Rec.709 gamma 2.2 输入及 BT.2020/PQ RGB10A2 位解包，最小实现位于 `nvidia/runtime.py`。本项目没有 ComfyUI 依赖、前端、节点树或工作流。

实际模型依赖 NVIDIA 官方二进制 wheel；核心环境不含 PyTorch 或 `nvvfx`，真实模型在项目根目录独立 `.venv-nvidia` 执行。合成中间结果与替代模型只用于接口、色彩转换和编码契约测试；`output/nvidia/run-001` 则是真实 TrueHDR 运行结果，二者在报告中区分。

## NVIDIA 官方模型

固定 `nvidia-vfx==0.2.0.0` 与 PyTorch 2.11.0+cu128，Windows x64、Python 3.12、独立 `.venv-nvidia`。官方 `TrueHDR` 输出 PQ/RGB10A2；本项目使用 PQ 公式解码绝对亮度后除以 203 尼特。本机 RTX 4070 Laptop、驱动 617.14 已真实执行一张夜景。默认流 `stream_ptr=0` 已实测可用，私有流会失败；CUDA uint32 先复制主机后由 NumPy 解包。`luminance` 是模型目标参数，不是像素硬上限。

## 编码底座

使用 Google 官方 libultrahdr v2.0.2（提交 `e5f5a022fe96fc4dc2ee35c19f733a50df807abe`），以及 libjpeg-turbo 3.2.0，均有固定来源与 SHA-256。桥接使用官方 API-3 从 HDR 中间结果与原始 SDR JPEG 生成标准 Ultra HDR。JPEG XR 使用 Windows WIC 原生浮点编解码；矩阵与峰值换算见 `color-pipeline.md`。
