# NVIDIA TrueHDR 直接执行与输出

## 直接运行

`enhance-nvidia` 直接调用官方 `nvvfx.TrueHDR`，不依赖 ComfyUI。要求 Windows x64、Python 3.12、隔离 `.venv-nvidia`、固定 `nvidia-vfx==0.2.0.0`、PyTorch 2.11.0+cu128 与支持 CUDA 的 NVIDIA GPU。本工具不自动安装依赖；本机真实夜景结果位于 `output/nvidia/run-001`。

```powershell
.venv-nvidia\Scripts\python.exe -m hdrview.cli enhance-nvidia <原始 JPEG> --contrast 100 --saturation 100 --middle-gray 50 --luminance 1000
```

默认启用去色带，`--no-debanding` 显式关闭。运行前严格检查 `nvidia-vfx==0.2.0.0`；模块版本不是有效字符串时回退读取发行包元数据。模型先读取带 ICC 的源图，转换到 Rec.709 gamma 2.2 输入；克隆输出后先校验 H×W 与 `uint32`，再解包 BT.2020/PQ 并转为共享线性 BT.2020/203-nit。

模型成功后先写入 `<原图 stem>-truehdr.f16rgba` 与 `<原图 stem>-truehdr.json`。报告的 `intermediate` 列出两个路径和原始照片 SHA-256，`nvidia_vfx`、`content_hdr_capacity_max` 与实际 HDR 一致。完整参数及 `gpu_executed=true` 仅在模型实际完成后写入报告；缺依赖、缺 CUDA、版本不匹配、模型失败或尺寸不匹配均在创建输出目录前失败，不生成伪结果。固定版本已实测要求官方默认 CUDA 流，RGB10A2 的 uint32 数据在主机 NumPy 解包，避免 PyTorch 2.11 的 CUDA 位运算限制。

## 已有中间结果

`convert-nvidia` 保留中间结果转换入口：

```powershell
python -m hdrview.cli convert-nvidia <原始 JPEG> --intermediate <中间结果 stem>
```

它校验原图 SHA-256、尺寸和 `pipeline=nvidia-truehdr`，`gpu_executed=false` 表示本次只转换，不否定中间结果曾经来自真实模型，也不制造 GPU 证据。

## 共享输出

两条 NVIDIA 命令使用与 vivo 相同的编码出口：默认 `output/nvidia/run-NNN`，400 与 1000 尼特 Ultra HDR JPEG，以及 HDR400 浮点 JPEG XR。HDR400 映射只执行一次，HDR1000 保留原内容；输出不覆盖已有文件。Windows Photos HDR 显示仍需手动验收，不能用 WIC 回读代替。

## AVIF 诊断边界

可选 10-bit AVIF PQ 不属于新管线默认输出；当前未实测其编码或显示。它不是 Ultra HDR/JPEG XR，也不自动具备完整 HDR10 主控元数据。
