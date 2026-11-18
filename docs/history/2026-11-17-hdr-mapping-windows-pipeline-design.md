# 高光显示映射、NVIDIA 直接执行与 Windows 原生 HDR 设计

本文记录历史设计。当前命令与输出目录见[项目说明](../../README.md)。

- 日期：2026-11-17
- 状态：用户已确认并实施。`feature/hdr-pipelines` 隔离工作区，真实 NVIDIA 夜景与 JPEG XR 已运行，Windows Photos 显示待用户验收
- 基线：`3cf276a`，80 项测试通过、2 项缺少 GPU 环境而跳过

## 目标与实测依据

保留 vivo 1000 尼特版本的细节，为 HDR400 屏幕增加更强的专用高光映射，改善相近亮区合并问题。NVIDIA 路线通过官方运行时执行 TrueHDR。每张结果同时支持标准 Ultra HDR JPEG 和 Windows 照片应用优先的 JPEG XR 浮点 HDR。

官方 libultrahdr v2.0.2 在 `jpegr.cpp:1678–1689` 按显示余量和 HDR 容量的对数比例应用增益。现有四张图的固定 HDR400 参考解码证实，1000 尼特版本的局部高光弱于 400 尼特版本。Luma 源码 `GainMap.h` 和 `Luma.Native.cpp` 使用同一映射，1 个 scRGB 单位为 80 尼特，中间线性单位为 203 尼特。

当前 vivo `reconstruct.py:36–40` 在辅助亮度阈值处硬切换，应改为连续、单调融合。该方法是待验证的重建候选。报告保持“合理 HDR 重建，手机 XDR 观感有待验证”。

## 统一处理与目录

沿用 Python 3.12、NumPy/OpenCV、线性 BT.2020、203 尼特参考白的中间表示。管线的输入哈希、参数、处理顺序、色彩与来源信息在报告中保留。不引入 ComfyUI 运行时、前端或自定义节点树。

```text
src/hdrview/
├─ cli.py                       # 命令行与任务分配
├─ model.py                     # 图像与色彩模型
├─ io/                          # 只读输入、中间结果、输出目录
├─ color/                       # ICC、色域与传递函数
├─ vivo/                        # 私有输入与候选高光融合
├─ nvidia/                      # 参数契约、直接模型运行、PQ 读回
├─ mapping.py                   # 共享显示高光压缩
└─ native/
   ├─ hdrview_ultrahdr.cpp      # 官方 libultrahdr API-3
   ├─ hdrview_jxr.cpp           # Windows WIC JPEG XR
   ├─ CMakeLists.txt
   └─ Build-Native.ps1
```

构建入口归入 `src/hdrview/native/`，模型入口归入 `src/hdrview/nvidia/runtime.py`，输入色彩处理由共享模块提供。常规导出使用 Ultra HDR JPEG 和浮点 JPEG XR，`output/avif.py` 用于独立诊断。

## 高光融合与 HDR400 映射

`ReconstructionParams` 保持原有四个字段。在 `reconstruct` 内用辅助亮度阈值的 `[threshold, 2*threshold]` 平滑步进权重替换硬切换。阈值为零时只对严格大于零的辅助像素启用。暗处仍不改变。该候选保留局部细节，vivo 私有遮罩的复现情况有待验证。

新增 `DisplayMapping(peak_nits=400, knee_ratio=0.8)` 和 `map_highlights(hdr, params) -> HdrImage`。输入和输出均为共享线性 BT.2020，单位为 203 尼特。只处理大于 1 的 HDR 光强，以 BT.2020 亮度比值调整 RGB，保护 SDR 范围：

```text
L = HDR 亮度，单位 203 nit
H = 目标峰值 / 203
K = 1 + (H - 1) * knee_ratio
L <= 1：不变
1 < L <= K：从 1 连续过渡到 K，初始斜率为 1
L > K：从 K 单调逼近 H，导数连续，不硬裁剪层次
```

归一化有理曲线保留相邻亮区的层次。设 `T = H-K`、`x=(L-K)/T`，则 `M=K+T*x/(1+x)`。低亮段 `1<L<=K` 保持 `M=L`。曲线严格单调，在 K 处与高亮段的函数值和导数均连续。RGB 按 `M/L` 缩放，保留通道比例和中间色域。峰值约束作用于 BT.2020 亮度，饱和色保留连续变化。原 JPEG 已削顶区域的细节取决于可用输入。

`--target-nits 400` 在编码前调用该映射，声明容量 `400/203≈1.97044`。`--target-nits 1000` 保留原 HDR 内容及 `1000/203≈4.92611` 的容量。报告记录 `display_mapping="hdr400-highlight-compression"` 或 `"none"`。原图只读，输出使用独立文件。报告中的容量按编码参数记录。

## NVIDIA 官方模型直接运行

固定 `nvidia-vfx==0.2.0.0`、Python 3.12、Windows x64、支持 CUDA 的 PyTorch，模型在隔离 `.venv-nvidia` 中安装。默认 `luminance=1000`，固定 PQ 输出、去色带开启，先可选超分、再 TrueHDR。

`TrueHdrParams` 定义参数范围与报告字段。`runtime.py` 通过 `nvvfx.TrueHDR` 和可选的 `nvvfx.VideoSuperRes` 调用 NVIDIA 官方模型。RGB10A2 解包及输出解释参考 Apache-2.0 的 Comfy-Org NVIDIA VFX Nodes 固定提交 `38d790ded00650681fa3645362efe28c8560cf40`，并在 `docs/research/source-audit.md` 明示来源。

首版直接模型命令 `enhance-nvidia <原图> [--contrast 100] [--saturation 100] [--middle-gray 50] [--luminance 1000]`。超分作为第二阶段，先核验实际 GPU 环境与 API，再提供参数。模型调用结果以实际运行为准。

真实运行必须检查 CUDA、固定版本、源图哈希、输出 H×W 尺寸、`uint32` RGB10A2 数据类型、有限数值与 BT.2020/PQ 输出。`enhance-nvidia` 在显示输出编码前保存 `<原图 stem>-truehdr.f16rgba` 与 `<原图 stem>-truehdr.json` 线性 HDR 中间结果，报告列出像素、元数据路径及原图 SHA-256，并记录实际 `nvidia-vfx` 版本和内容容量。以实测像素和声明目标分别记录容量。将 luminance 记录为目标参数。CUDA 或 nvvfx 缺失时明确标记真实测试已跳过。

## Windows 照片应用 HDR：JPEG XR

选择系统 WIC 原生支持的 JPEG XR，作为 Windows 显示输出格式。新增独立 Windows C++ 编码/解码桥接：输入严格校验 `rgba-float16` BT.2020 linear sidecar，转换为 scRGB Rec.709 线性光。203 nit 单位乘以 `203/80`，输出 WIC `GUID_WICPixelFormat64bppRGBAHalf` JPEG XR。

JPEG XR 容器由 WIC 生成，色彩信息使用受支持的格式。BT.2020 转 Rec.709 使用数值逆矩阵，保留 scRGB 允许的负分量。编码请求 WIC 最高 `ImageQuality`。已测试的无损及 4:4:4 请求实测收益为零，已从实现移除。浮点格式契约描述输入输出格式，编码内部位深与无损性需独立验证。输出使用独立 `*-400nit.jxr` 文件名。先写临时文件，成功关闭 WIC 后原子移动。拒绝已有输出。通过 Windows WIC 解码读取同一文件，检查浮点格式、尺寸、中性色与饱和色误差、高光像素仍大于 SDR 参考值。编码报告中的 `jxr_sha256` 是 JPEG XR 文件字节哈希，对应 JPEG XR 编码结果。

参考微软 Windows Imaging Component 的浮点 JPEG XR 文档选择编码格式，参考 Luma 0.1.32 的 MIT 许可源码理解浮点 JPEG XR 的显示处理。Windows 照片应用的显示效果以实机对照为准。

## 验证责任

- 单元测试：vivo 阈值两侧连续、暗区不变、融合有限且不超过增益上限。HDR400 映射单调、不超过目标、SDR 不变、暗部稳定、保留相邻层次。
- 原生集成测试：真实构建 WIC 编码器，JPEG XR 可由 WIC 浮点解码，高光未被量化成 SDR。已有输出拒绝覆盖。
- 管线集成测试：400 与 1000 报告区分映射参数和实际容量。JPEG 与 JPEG XR 来自同一映射内容。原始照片哈希不变。
- NVIDIA 测试：使用替代模型接口验证调用顺序、参数传播与 PQ 转换。真实 GPU 执行只在固定环境安装后运行，并显式记录证据。
- 用户验收使用 Luma 比较新旧 400 尼特与 1000 尼特高光，使用 Windows 照片应用对照 JPEG XR 的原生高动态范围显示。

## 实施范围

当时的交付范围为本地文件和命令行工具。原图保持只读，测试脚本在完成后清理。NVIDIA 运行时直接调用官方模型，位解包参考 Comfy-Org 的节点源码。vivo 参数用于候选高光重建。JPEG XR 和 Ultra HDR JPEG 通过格式与回读测试，手机相册及 Windows 照片应用按实机对照验收。
