# ComfyUI NVIDIA TrueHDR 工作流

## 固定环境

- Windows 11 x64；RTX 4070 Laptop（8 GiB）。
- Python 3.12，独立于 HDR-view 核心环境。
- ComfyUI ≥0.35.0（需要 `ImageColorSpace` 与 AVIF PQ 支持）。
- ComfyUI NVIDIA VFX Nodes 0.2.1，固定提交 `38d790ded00650681fa3645362efe28c8560cf40`。
- CUDA 启用的 PyTorch `cu130+`；NVIDIA 驱动≥570.65。
- `nvidia-vfx>=0.2`；实际 wheel 来自 NVIDIA 官方索引 `https://pypi.nvidia.com`，模型/运行库随 wheel 分发。

## 安装边界

ComfyUI、PyTorch、NVIDIA wheel 和本项目的自定义节点应在独立环境中安装。不要修改 HDR-view 的核心 Python 环境，也不要将未知第三方 Ultra HDR 节点混入工作流。具体下载/安装前需用户确认版本、来源和目标目录。

## 工作流链路

```text
LoadImage（项目预先生成的标准 sRGB PNG）
→ HdrViewPrepareTrueHDR（sRGB → Rec.709/D65 gamma 2.2）
→ 官方 RTXTrueHDR（PQ、去色带、400 nit 初始参数）
→ HdrViewSaveLinear（PQ → 线性 BT.2020 + sidecar）
```

`comfyui/workflows/nvidia_to_hdr.json` 定义该链路；不会把普通 Save Image 或 AVIF 当作 Ultra HDR。手机原始 JPEG 的 Display-P3 必须先由核心 ICC 解码处理，不使用 ComfyUI 默认的 `convert('RGB')` 替代 ICC。

## 当前验证状态

自定义节点已提供，但尚未在 ComfyUI 中导入或执行；没有实测的 GPU 占用、显存、速度或 AI 输出效果。核心测试不安装 PyTorch/nvvfx 时明确跳过 GPU 集成，不报告虚假通过。

## 输出

节点保存线性 HDR 中间结果，不直接写 Ultra HDR。随后用项目命令 `convert-nvidia` 将中间结果与原始 SDR JPEG 一起交给共享官方 libultrahdr 编码器。Luma 仅用于最终原生 HDR 显示对照，不用截图代替数据导出。
