# NVIDIA TrueHDR 与照片增强

## 安装环境

运行模型需要 64 位 Windows、Python 3.12、兼容的 NVIDIA 显卡和驱动。从源码运行时，按[项目说明](../../README.md#从源码运行)构建原生编码组件，再在独立环境中安装模型所需的软件包。

```powershell
py -3.12 -m venv .venv-nvidia
.\.venv-nvidia\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install --only-binary=:all: nvidia-vfx==0.2.0.0 --index-url https://pypi.nvidia.com
python -c "import torch, nvvfx; print(torch.cuda.is_available())"
```

本项目使用 PyTorch 2.11.0 的 CUDA 12.8 构建，以及包含 TrueHDR 的 NVIDIA 视频效果软件包 0.2.0.0。环境检查应输出 `True`。安装命令参考 [PyTorch 安装说明](https://pytorch.org/get-started/previous-versions/#v2110)和 [NVIDIA 软件包说明](https://pypi.org/project/nvidia-vfx/0.2.0.0/)。使用可执行文件时，按[单文件发行版说明](../windows-release.md#nvidia-模型)设置解释器路径。

## 批量增强

```powershell
hdrview enhance-nvidia ".\images\photos"
hdrview enhance-nvidia ".\images\photos" --vsr --vsr-scale 2 -o ".\results\upscaled"
hdrview enhance-vsr ".\images\photos" --vsr-mode denoise -o ".\results\denoised"
```

`enhance-nvidia` 调用 NVIDIA 官方 TrueHDR。默认参数为 `--contrast 100 --saturation 100 --middle-gray 50 --luminance 1000`，默认启用去色带，可通过 `--no-debanding` 关闭。线性高动态范围中间文件使用 `原图名-truehdr` 前缀，报告记录原图哈希、模型参数、内容容量及运行来源。

`enhance-nvidia --vsr` 先处理照片，再执行 TrueHDR，并保存增强后的 `原图名-VSR-base.jpg` 作为编码基础图。独立命令 `enhance-vsr` 输出标准动态范围的 `原图名-VSR.jpg` 和报告。

| 参数 | 取值 |
| --- | --- |
| `--vsr-mode` | `upscale` 放大（默认）、`denoise` 去噪、`deblur` 去模糊 |
| `--vsr-scale` | 放大模式支持 2、3、4 倍，默认 2。去噪和去模糊固定保留原尺寸 |
| `--vsr-quality` | `low`、`medium`、`high`（默认）、`ultra` |
| `--vsr-strength` | 0 至 1，默认 1 |

输出最长边上限为 16384 像素，总像素上限为 134217728。

## 复用已有中间结果

```powershell
hdrview convert-nvidia ".\images\photos" --intermediate ".\output\nvidia" -o ".\results\reencoded" --target-nits 400
hdrview convert-nvidia ".\images\photo.jpg" --intermediate ".\output\nvidia\photo-truehdr.f16rgba" -o ".\results\single"
```

批量转换时，`--intermediate` 指向存放 `原图名-truehdr.f16rgba` 和 `原图名-truehdr.json` 的目录。中间结果绑定增强基础图时，命令在该目录查找 `原图名-VSR-base.jpg`，也可用 `--sdr-base` 指定其他基础图目录。单图转换接受中间文件、去掉扩展名的路径或中间结果目录，基础图可指定具体文件。

重编码校验原图哈希、图像尺寸和派生基础图哈希，报告记录输入中间文件的路径、哈希及可读取的增强参数。重编码任务通过 `gpu_executed=false` 标记来源，模型实际运行后报告记录 `gpu_executed=true`。

转换与增强默认写入当前目录下的 `output/nvidia`。可使用 `-o` 保存同一照片的新一轮结果。TrueHDR 输出默认为 1000 尼特 Ultra HDR JPEG，选择 400 尼特时同时输出浮点 JPEG XR。格式测试见[验证记录](../verification.md)，色彩处理和模型调用参考见[上游来源](../research/source-audit.md)。
