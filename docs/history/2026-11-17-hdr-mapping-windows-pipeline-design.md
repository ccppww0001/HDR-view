# 高光显示映射、NVIDIA 直接执行与 Windows 原生 HDR 设计

本文记录历史设计。当前命令与输出目录见[项目说明](../../README.md)。

- 日期：2026-11-17
- 状态：用户已确认并实施；`feature/hdr-pipelines` 隔离工作区，真实 NVIDIA 夜景与 JPEG XR 已运行，Windows Photos 显示待用户验收
- 基线：`3cf276a`，80 项测试通过、2 项缺少 GPU 环境而跳过

## 目标与实测依据

保留 vivo 1000 尼特版本的细节，为 HDR400 屏幕增加更强的专用高光映射，改善相近亮区合并问题。NVIDIA 路线直接使用官方模型，不依赖 ComfyUI。每张结果同时支持标准 Ultra HDR JPEG 和 Windows 照片应用优先的 JPEG XR 浮点 HDR。

官方 libultrahdr v2.0.2 在 `jpegr.cpp:1678–1689` 按显示余量和 HDR 容量的对数比例应用增益。现有四张图的固定 HDR400 参考解码证实，1000 尼特版本的局部高光弱于 400 尼特版本。Luma 源码 `GainMap.h` 和 `Luma.Native.cpp` 使用同一映射，1 个 scRGB 单位为 80 尼特，中间线性单位为 203 尼特。

当前 vivo `reconstruct.py:36–40` 在辅助亮度阈值处硬切换，应改为连续、单调融合；这不是 vivo 官方算法。报告保持“合理 HDR 重建，手机 XDR 观感未验证”。

## 统一处理与目录

沿用 Python 3.12、NumPy/OpenCV、线性 BT.2020、203 尼特参考白的中间表示。管线的输入哈希、参数、处理顺序、色彩与来源信息在报告中保留；不引入 ComfyUI 运行时、前端或自定义节点树。

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

移除 `src/hdrview/build/`、`src/hdrview/comfyui/` 和 `src/hdrview/nvidia/comfy_workflow.py`。旧的 `input.py` PNG 导出不再用于模型输入；只有仍有独立价值的函数才保留并改说明。原 `output/avif.py` 暂保留诊断能力，但不作为 Windows HDR 已验证路径，也不放进新管线默认输出。

## 高光融合与 HDR400 映射

`ReconstructionParams` 保持原有四个字段；在 `reconstruct` 内用辅助亮度阈值的 `[threshold, 2*threshold]` 平滑步进权重替换硬切换。阈值为零时只对严格大于零的辅助像素启用。暗处仍不改变；无高通量图像模糊，不宣称复现 vivo 私有遮罩。

新增 `DisplayMapping(peak_nits=400, knee_ratio=0.8)` 和 `map_highlights(hdr, params) -> HdrImage`。输入和输出均为共享线性 BT.2020，单位为 203 尼特。只处理大于 1 的 HDR 光强，以 BT.2020 亮度比值调整 RGB，保护 SDR 范围：

```text
L = HDR 亮度，单位 203 nit
H = 目标峰值 / 203
K = 1 + (H - 1) * knee_ratio
L <= 1：不变
1 < L <= K：从 1 连续过渡到 K，初始斜率为 1
L > K：从 K 单调逼近 H，导数连续，不硬裁剪层次
```

为避免“相近亮区映射在一起”及局部过饱和，采用归一化有理曲线，而不是对数近似：设 `T = H-K`，`x=(L-K)/T`，则 `M=K+T*x/(1+x)`。低亮段 `1<L<=K` 保持 `M=L`；在 K 处与高亮段函数值、导数均连续，并严格单调。RGB 按 `M/L` 缩放，允许比 SDR 基础更广的中间色域，保持原比例；峰值约束作用于 BT.2020 亮度而不是每个通道，饱和色不会被硬裁剪。不会凭空恢复已削顶的原 JPEG 细节。

`--target-nits 400` 在编码前调用该映射，声明容量 `400/203≈1.97044`；`--target-nits 1000` 保留原 HDR 内容及 `1000/203≈4.92611` 的容量。报告记录 `display_mapping="hdr400-highlight-compression"` 或 `"none"`。不修改原图、不覆盖输出，不声称实际物理亮度已由仪器测量。

## NVIDIA 官方模型直接运行

固定 `nvidia-vfx==0.2.0.0`、Python 3.12、Windows x64、支持 CUDA 的 PyTorch，模型在隔离 `.venv-nvidia` 中安装。默认 `luminance=1000`，固定 PQ 输出、去色带开启，先可选超分、再 TrueHDR。

`TrueHdrParams` 继续承担参数范围和报告契约，但 `output_colorspace` 不再是伪工作流选项。新增 `runtime.py`，真实运行器通过 `nvvfx.TrueHDR` 和可选 `nvvfx.VideoSuperRes` 调用官方模型；不依赖 ComfyUI。RGB10A2 解包及输出解释参考 Apache-2.0 的 Comfy-Org NVIDIA VFX Nodes 固定提交 `38d790ded00650681fa3645362efe28c8560cf40`，并在 `docs/research/source-audit.md` 明示来源。

首版直接模型命令 `enhance-nvidia <原图> [--contrast 100] [--saturation 100] [--middle-gray 50] [--luminance 1000]`。超分作为第二阶段，先核验实际 GPU 环境与 API，再提供参数；不能把未经运行的模型调用称为成功。

真实运行必须检查 CUDA、固定版本、源图哈希、输出 H×W 尺寸、`uint32` RGB10A2 数据类型、有限数值与 BT.2020/PQ 输出。`enhance-nvidia` 在显示输出编码前保存 `<原图 stem>-truehdr.f16rgba` 与 `<原图 stem>-truehdr.json` 线性 HDR 中间结果，报告列出像素、元数据路径及原图 SHA-256，并记录实际 `nvidia-vfx` 版本和内容容量。以实测像素和声明目标分别记录容量；不把 luminance 当硬上限。没有 CUDA/nvvfx 时明确跳过真实测试。

## Windows 照片应用 HDR：JPEG XR

选择系统 WIC 原生支持的 JPEG XR，而非未经证实的 AVIF 显示承诺。新增独立 Windows C++ 编码/解码桥接：输入严格校验 `rgba-float16` BT.2020 linear sidecar，转换为 scRGB Rec.709 线性光；203 nit 单位乘以 `203/80`，输出 WIC `GUID_WICPixelFormat64bppRGBAHalf` JPEG XR。

不手工写 JPEG XR 二进制容器，不注入未经支持的 PQ/HDR10 标签。BT.2020 转 Rec.709 使用数值逆矩阵而非转置，保留 scRGB 允许的负分量；编码请求 WIC 最高 `ImageQuality`。已测试的无损及 4:4:4 请求没有实测收益，已从实现移除；浮点格式契约不等于编码内部位深或无损证明。输出使用独立 `*-400nit.jxr` 文件名。先写临时文件，成功关闭 WIC 后原子移动；拒绝已有输出。通过 Windows WIC 解码读取同一文件，检查浮点格式、尺寸、中性色与饱和色误差、高光像素仍大于 SDR 参考值。编码报告中的 `jxr_sha256` 是 JPEG XR 文件字节哈希，不是原始照片 SHA-256。

微软官方资料证明 WIC 的 JPEG XR 浮点编码及 HDR 支持，并建议 HDR 捕获内容保存为 JPEG XR；Luma v0.1.32 将 JPEG XR 浮点源解释为 HDR。Windows Photos 实际 HDR 显示仍需要用户手动验证；不把能解码或能打开当作显示验证。参考 Luma MIT 源码时记录来源，避免复制整个查看器。

## 验证责任

- 单元测试：vivo 阈值两侧连续、暗区不变、融合有限且不超过增益上限；HDR400 映射单调、不超过目标、SDR 不变、暗部稳定、保留相邻层次。
- 原生集成测试：真实构建 WIC 编码器，JPEG XR 可由 WIC 浮点解码，高光未被量化成 SDR；已有输出拒绝覆盖。
- 管线集成测试：400 与 1000 报告区分映射参数和实际容量；JPEG 与 JPEG XR 来自同一映射内容；原始照片哈希不变。
- NVIDIA 测试：使用替代模型接口验证调用顺序、参数传播与 PQ 转换；真实 GPU 执行只在固定环境安装后运行，并显式记录证据。
- 用户验收：Luma 比较新旧 HDR400/1000 高光，Windows Photos 打开 JPEG XR 检查原生 HDR；目前不保证达到任一主观效果。

## 非目标

不制作界面、不操作桌面或启动应用；不修改原始照片；不推送远程；不保留临时测试脚本；不把开源节点的调用方式等同于 ComfyUI 依赖；不将 vivo 参数称为官方 XDR 算法；不将 JPEG XR 或 Ultra HDR JPEG 的格式验证等同于手机观感或 Windows Photos 显示验证。
