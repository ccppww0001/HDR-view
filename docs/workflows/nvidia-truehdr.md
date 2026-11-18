# NVIDIA TrueHDR 与照片增强

## 安装环境

按[项目说明](../../README.md)准备 64 位 Windows、Python 3.12 和原生编码组件。运行模型还需兼容的 NVIDIA 显卡与驱动。建议在独立环境中安装模型依赖：

```powershell
py -3.12 -m venv .venv-nvidia
.\.venv-nvidia\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install --only-binary=:all: nvidia-vfx==0.2.0.0 --index-url https://pypi.nvidia.com
python -c "import torch, nvvfx; print(torch.cuda.is_available())"
```

PyTorch 使用本项目验证过的 CUDA 12.8 构建。NVIDIA 软件包固定到引入 TrueHDR 的发行版。最后一条命令应打印 `True`。详见 [PyTorch 安装说明](https://pytorch.org/get-started/previous-versions/#v2110)和 [NVIDIA 软件包说明](https://pypi.org/project/nvidia-vfx/0.2.0.0/)。

## 批量增强

```powershell
hdrview enhance-nvidia ".\images\photos"
hdrview enhance-nvidia ".\images\photos" --vsr --vsr-scale 2 -o ".\results\upscaled"
hdrview enhance-vsr ".\images\photos" --vsr-mode denoise -o ".\results\denoised"
```

`enhance-nvidia` 调用官方 TrueHDR，默认参数为 `--contrast 100 --saturation 100 --middle-gray 50 --luminance 1000`，默认启用去色带，可用 `--no-debanding` 关闭。生成的线性高动态范围中间文件以 `原图名-truehdr` 开头。报告记录原图哈希、实际模型参数、内容容量及 `gpu_executed`。

`enhance-nvidia --vsr` 先增强照片，再执行 TrueHDR，并保存增强后的 `原图名-VSR-base.jpg` 作为编码基础图。独立的 `enhance-vsr` 输出 `原图名-VSR.jpg` 和报告。

| 参数 | 取值 |
| --- | --- |
| `--vsr-mode` | `upscale` 放大（默认）、`denoise` 去噪、`deblur` 去模糊 |
| `--vsr-scale` | 放大支持 2、3、4 倍，默认 2。去噪和去模糊保持原尺寸，请省略此参数 |
| `--vsr-quality` | `low`、`medium`、`high`（默认）、`ultra` |
| `--vsr-strength` | 0 至 1，默认 1 |

输出最长边为 16384 像素，总像素最多为 134217728。

## 复用已有中间结果

```powershell
hdrview convert-nvidia ".\images\photos" --intermediate ".\output\nvidia" -o ".\results\reencoded" --target-nits 400
hdrview convert-nvidia ".\images\photo.jpg" --intermediate ".\output\nvidia\photo-truehdr.f16rgba" -o ".\results\single"
```

批量转换时，`--intermediate` 指向含有 `原图名-truehdr.f16rgba` 和 `原图名-truehdr.json` 的目录。若中间结果绑定增强后的基础图，命令会在该目录查找 `原图名-VSR-base.jpg`，也可使用 `--sdr-base` 指定另一个基础图目录。单图转换也接受具体的中间文件路径、去掉扩展名的路径，以及具体的基础图路径。

转换时校验原图哈希、图像尺寸和派生基础图哈希。报告记录输入中间文件的路径与哈希、已有的增强参数，并标记本次为重编码（`gpu_executed=false`）。缺少部分可选增强参数的旧中间文件仍可读取。

转换和增强默认直接写入当前目录下的 `output/nvidia`。重新导出已有照片时，使用 `-o` 指定另一目录可以避免同名产物冲突。默认导出 1000 尼特 Ultra HDR JPEG，选择 400 尼特时还会输出浮点 JPEG XR。格式回读与 Windows 显示验收见[验证记录](../verification.md)，色彩处理与模型调用来源见[上游来源](../research/source-audit.md)。
