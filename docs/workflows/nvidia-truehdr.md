# NVIDIA TrueHDR 直接执行与输出

## 直接运行

`enhance-nvidia` 直接调用官方 `nvvfx.TrueHDR`，不依赖 ComfyUI。要求 Windows x64、Python 3.12、隔离 `.venv-nvidia`、固定 `nvidia-vfx==0.2.0.0`、PyTorch 2.11.0+cu128 与支持 CUDA 的 NVIDIA GPU。本工具不自动创建环境或安装依赖；本机真实夜景结果位于 `output/nvidia/run-001`。

```powershell
$env:PYTHONPATH = 'src'
.venv-nvidia\Scripts\python.exe -m hdrview.cli enhance-nvidia <原始 JPEG> --contrast 100 --saturation 100 --middle-gray 50 --luminance 1000
```

默认启用去色带，`--no-debanding` 显式关闭。运行前严格检查 `nvidia-vfx==0.2.0.0`；模块版本不是有效字符串时回退读取发行包元数据。模型先读取带 ICC 的源图，转换到 Rec.709 gamma 2.2 输入；克隆输出后先校验 H×W 与 `uint32`，再解包 BT.2020/PQ 并转为共享线性 BT.2020/203-nit。

模型成功后先写入 `<原图 stem>-truehdr.f16rgba` 与 `<原图 stem>-truehdr.json`。报告的 `intermediate` 列出两个路径和原始照片 SHA-256，`nvidia_vfx`、`content_hdr_capacity_max` 与实际 HDR 一致。完整参数及 `gpu_executed=true` 仅在模型实际完成后写入报告；缺依赖、缺 CUDA、版本不匹配、模型失败或尺寸不匹配均在创建输出目录前失败，不生成伪结果。固定版本已实测要求官方默认 CUDA 流，RGB10A2 的 uint32 数据在主机 NumPy 解包，避免 PyTorch 2.11 的 CUDA 位运算限制。

## 可选的视频超分辨率增强

`enhance-nvidia --vsr` 在 TrueHDR 之前调用官方 `nvvfx.VideoSuperRes`；默认关闭，原有 TrueHDR 参数、颜色预处理与 1000 尼特默认输出保持不变。独立命令 `enhance-vsr` 使用相同增强参数，只导出增强后的标准 sRGB JPEG 和报告，不执行 TrueHDR。

```powershell
.venv-nvidia\Scripts\python.exe -m hdrview.cli enhance-nvidia <原始 JPEG> --vsr --vsr-mode upscale --vsr-scale 2 --vsr-quality high --vsr-strength 1
.venv-nvidia\Scripts\python.exe -m hdrview.cli enhance-vsr <原始 JPEG> --vsr-mode denoise --vsr-quality high --vsr-strength 1
```

- `--vsr-mode`：`upscale` 放大、`denoise` 去噪或 `deblur` 去模糊，默认 `upscale`。
- `--vsr-scale`：默认 2；放大支持整数 2、3、4 倍，去噪和去模糊固定为 1 倍。
- `--vsr-quality`：`low`、`medium`、`high` 或 `ultra`，默认 `high`，对应官方 `QualityLevel`。
- `--vsr-strength`：范围 0 到 1，默认 1。

输出最长边不超过 16384 像素，总像素不超过 128 Mi。质量等级来自官方接口；图库照片的实际效果需要对照原图逐张评估。增强结果经伽马 2.2 转回 sRGB，保存为派生基础 JPEG，不替换原图。报告保留原图哈希和尺寸、实际增强参数与派生基础图哈希。

对于经过增强的 TrueHDR 中间结果，`convert-nvidia` 必须指定 `--sdr-base <本次增强派生 JPEG>`，并校验派生基础图哈希。

```powershell
.venv-nvidia\Scripts\python.exe -m hdrview convert-nvidia <原始 JPEG> --intermediate <结果目录/原图名-truehdr> --sdr-base <结果目录/原图名-VSR-base.jpg>
```

`--intermediate` 可使用完整 stem，或对应 `.json` / `.f16rgba` 路径。名称中的其他点号完整保留。重编码报告的 `intermediate_input` 记录输入像素文件与元数据文件的绝对路径、各自 SHA-256，`vsr` 保留原增强模式、倍数、质量和强度，并标明本轮没有重新执行模型。缺少这些可选参数的旧中间文件仍可读取，报告只保留已知字段。

## 已有中间结果

`convert-nvidia` 保留中间结果转换入口：

```powershell
$env:PYTHONPATH = 'src'
python -m hdrview.cli convert-nvidia <原始 JPEG> --intermediate <中间结果 stem>
```

它校验原图 SHA-256、尺寸和 `pipeline=nvidia-truehdr`，`gpu_executed=false` 表示本次只转换，不否定中间结果曾经来自真实模型，也不制造 GPU 证据。

源文件、模型和参数检查失败时结果目录尚未创建；最终编码阶段发生在新运行目录创建之后。如果编码失败，可保留该次中间文件供排查，并在重新运行时分配新的运行目录。成功标志以命令退出状态与完整 `report.json` 为准。

## 共享输出

两条 NVIDIA 命令使用与 vivo 相同的编码出口：默认 `output/nvidia/run-NNN`，默认输出 1000 尼特 Ultra HDR JPEG。使用 `--target-nits 400` 可输出 400 尼特 Ultra HDR JPEG 与浮点 JPEG XR；使用 `--target-nits 400 1000` 可同时输出两个目标。HDR400 映射只执行一次，HDR1000 保留原内容；输出不覆盖已有文件。Windows Photos HDR 显示仍需手动验收，不能用 WIC 回读代替。

## AVIF 诊断边界

可选 10-bit AVIF PQ 不属于新管线默认输出；当前未实测其编码或显示。它不是 Ultra HDR/JPEG XR，也不自动具备完整 HDR10 主控元数据。
