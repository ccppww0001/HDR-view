# HDR-view：vivo 重建与 NVIDIA TrueHDR

本项目使用共享的线性 BT.2020、203 尼特参考白中间表示，分别处理 vivo 私有辅助图候选重建与 NVIDIA 官方 TrueHDR 直接模型。默认输出 1000 尼特 Ultra HDR JPEG；选择 400 尼特时同时输出 Windows 原生浮点 JPEG XR。两条路线互不串联，不需要 ComfyUI。

vivo 输出始终是**合理 HDR 重建，手机 XDR 观感未验证**。NVIDIA 已在本机真实执行一张夜景，结果见 `output/nvidia/run-001`；缺少依赖或 CUDA 时 `enhance-nvidia` 明确失败，不创建输出目录。Windows Photos 的 JPEG XR 显示效果和两条路线的视觉优劣仍需用户手动验收。

## 构建与命令

构建入口统一位于 `src/hdrview/native/Build-Native.ps1`：

```powershell
$env:HDRVIEW_TOOL_DIR = 'C:\Users\N452\AppData\Local\Temp\opencode\hdrview-build'
pwsh -File src/hdrview/native/Build-Native.ps1 -Test
$env:PYTHONPATH = 'src'
.venv-nvidia\Scripts\python.exe -m hdrview.cli convert-vivo <原始 Neo9 Pro JPEG>
.venv-nvidia\Scripts\python.exe -m hdrview.cli convert-nvidia <原始 JPEG> --intermediate <中间结果 stem>
.venv-nvidia\Scripts\python.exe -m hdrview.cli enhance-nvidia <原始 JPEG>
```

`enhance-nvidia` 要求隔离 `.venv-nvidia` 中的 `nvidia-vfx==0.2.0.0`、PyTorch 2.11.0+cu128 和可用 NVIDIA CUDA 设备。项目不会自动创建该环境或安装依赖；环境准备完成后的参数示例：

```powershell
$env:PYTHONPATH = 'src'
.venv-nvidia\Scripts\python.exe -m hdrview.cli enhance-nvidia <原始 JPEG> --contrast 100 --saturation 100 --middle-gray 50 --luminance 1000 --no-debanding
```

`--no-debanding` 仅在指定时关闭去色带。运行前严格检查固定版本，模型输出必须为源图 H×W 的 `uint32` RGB10A2。成功后先保存 `*-truehdr.f16rgba` 和 `*-truehdr.json`；报告记录中间文件路径、输入 SHA-256、实际 NVIDIA 版本、实际内容容量、TrueHDR 参数和 `gpu_executed`。读取已有中间结果的 `convert-nvidia` 不会声称本次执行了 GPU。

## NVIDIA 视频超分辨率增强

`enhance-nvidia --vsr` 调用 NVIDIA 官方 `nvvfx.VideoSuperRes`，先增强照片再执行 TrueHDR。默认关闭，原有 TrueHDR 参数、颜色预处理和 1000 尼特默认输出保持不变。独立的 `enhance-vsr` 只输出增强后的标准 sRGB JPEG 和报告。

```powershell
.venv-nvidia\Scripts\python.exe -m hdrview.cli enhance-nvidia <原始 JPEG> --vsr --vsr-mode upscale --vsr-scale 2 --vsr-quality high --vsr-strength 1
.venv-nvidia\Scripts\python.exe -m hdrview.cli enhance-vsr <原始 JPEG> --vsr-mode denoise --vsr-quality high --vsr-strength 1
```

`--vsr-mode` 支持 `upscale`、`denoise` 和 `deblur`，默认 `upscale`；`--vsr-scale` 默认 2，放大支持整数 2、3、4 倍，去噪和去模糊保持原尺寸。`--vsr-quality` 支持 `low`、`medium`、`high`、`ultra`，默认 `high`，对应官方质量等级；`--vsr-strength` 范围为 0 到 1，默认 1。输出最长边不超过 16384 像素，总像素不超过 128 Mi。图库照片效果需要逐图对比。

增强输出经伽马 2.2 转回 sRGB，保存为派生基础 JPEG，原图保留。报告记录原图哈希和尺寸、实际增强参数及派生基础图哈希。转换经过增强的 TrueHDR 中间文件时，`convert-nvidia` 需要通过 `--sdr-base <本次增强派生 JPEG>` 提供基础图并校验哈希。详细说明见 [NVIDIA 工作流](docs/workflows/nvidia-truehdr.md)。

## 输出与 HDR400 映射

默认输出为当前项目 `output/<任务>/run-NNN`，每次创建新目录，不覆盖历史文件。默认生成 1000 尼特 JPEG 和报告；选择 400 尼特时生成对应 JPEG 与 JPEG XR：

- `*-UltraHDR-400nit.jpg`：HDR400 高光压缩后的标准 Ultra HDR，容量为 `400/203`。
- `*-UltraHDR-1000nit.jpg`：未经 HDR400 压缩的原始 HDR 内容，容量为 `1000/203`。
- `*-HDR-400nit.jxr`：与 HDR400 JPEG 相同映射内容的 Windows WIC 浮点 JPEG XR。
- `report.json`：来源、参数、映射、实际容量和验证边界。

HDR400 映射仅处理大于 203 尼特参考白的高光，保护 SDR 范围；同一个映射结果交给 JPEG 和 JPEG XR 编码，不重复应用。`--target-nits 400` 选择 400 尼特，`--target-nits 400 1000` 同时选择两个目标。容量是编码元数据中的 HDR/SDR 倍率，不是仪器测得的物理亮度；JPEG XR 报告的 `content_max_bt2020` 与 `native_content_max` 是回读内容峰值，`jxr_sha256` 是 JPEG XR 文件字节哈希，与原始照片 SHA-256 分开命名。

## 显示验证

Ultra HDR JPEG 同时写入 ISO 21496-1 与 XMP；此前的 Luma 用户验收已能识别原生 HDR。JPEG XR 使用 Rec.709 scRGB 浮点像素，参考白 80 尼特，不等同于 PQ AVIF，也不等于 HDR10 主控内容。

在启用 Windows HDR 的兼容显示器上，用 Windows Photos 手动打开新生成的 `*-HDR-400nit.jxr`，检查高光、暗部与颜色；用 Luma 对照 HDR400 和 HDR1000 JPEG。当前报告固定 `windows_photos_hdr_verified=false`，格式解码成功不代表主观显示已验证。

## 诊断与验证

```powershell
$env:PYTHONPATH = 'src'
python -m hdrview.cli inspect <JPEG 或目录>
python -m hdrview.cli analyze-vivo <vivo 原始 JPEG>
python -m hdrview.cli reconstruct-vivo <vivo 原始 JPEG>
python -m hdrview.cli verify <Ultra HDR JPEG 或输出目录> --json <新验证报告路径>
.venv-nvidia\Scripts\python.exe -m pytest
```

源码结构与调用链见 [项目结构](docs/structure.md)。所有输出固定 `xdr_appearance_verified=false` 或同等明确的研究边界。设计与验证记录见 `docs/superpowers/specs/2026-11-17-hdr-mapping-windows-pipeline-design.md`、`docs/workflows/` 和 `docs/verification.md`。
