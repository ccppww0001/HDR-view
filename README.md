# HDR-view

HDR-view 是一个面向 Windows 的照片处理工具。它可以利用 iQOO Neo9 Pro 原图中的 vivo 私有辅助图重建高光，也可以用 NVIDIA TrueHDR 增强普通照片。两条路线都支持批量生成 Ultra HDR JPEG。

## 快速开始

在仓库根目录打开 PowerShell 7。准备 64 位 Windows、Python 3.12 和 Visual Studio 的「使用 C++ 的桌面开发」工作负载（含 CMake）。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
.\src\hdrview\native\Build-Native.ps1 -ToolDirectory (Join-Path (Get-Location) '.tools') -Test
hdrview --help
```

把示例路径换成你的原图或目录。vivo 转换使用上述环境，NVIDIA 增强需先完成 [NVIDIA 环境安装](docs/workflows/nvidia-truehdr.md#安装环境)。

```powershell
hdrview convert-vivo ".\images\vivo-photos"
hdrview enhance-nvidia ".\images\photos" -o ".\results"
hdrview enhance-vsr ".\images\a.jpg" ".\images\b.jpeg" --vsr-mode denoise
```

## 输入与输出

输入可以是一个或多个 JPEG 文件、目录，或两者的组合。目录只读取当前层的 `.jpg` 与 `.jpeg`，扩展名大小写均可。路径含空格时加引号。

| 功能 | 命令 | 省略输出参数时的目录 |
| --- | --- | --- |
| vivo 高光重建并导出 | `convert-vivo` | `output/vivo` |
| vivo 重建中间结果 | `reconstruct-vivo` | `output/vivo` |
| NVIDIA TrueHDR 增强并导出 | `enhance-nvidia` | `output/nvidia` |
| 复用 NVIDIA 中间结果导出 | `convert-nvidia` | `output/nvidia` |
| NVIDIA 照片放大、去噪或去模糊 | `enhance-vsr` | `output/nvidia` |

`vivo` 是私有辅助图的格式标识。当前验证设备为 [iQOO Neo9 Pro](https://www.vivo.com.cn/vivo/param/iqooneo9pro)。

默认目录相对于运行命令的位置。`-o`、`--output-dir` 或 `--output` 都可指定实际输出目录，例如 `-o ".\results"`。图片、相关中间文件和每张图的 `原图名-命令名-report.json` 直接保存在同一目录。

同一批次的原图需要使用不同的文件主名，例如 `a.jpg` 与 `a.jpeg` 会冲突。已有同名产物时，命令退出并报告冲突。重新处理同一张图时，可以通过 `-o` 选用另一目录。整批编码完成后才写入目标目录，原图保持只读。

批量处理 iQOO Neo9 Pro 照片时，程序会列出并跳过没有私有辅助图的文件。存在损坏或暂未支持的辅助图结构时，批次会停止并报告对应文件。

常用转换默认生成 1000 尼特 Ultra HDR JPEG。指定 `--target-nits 400` 后导出 400 尼特 Ultra HDR JPEG 和浮点 JPEG XR，指定 `--target-nits 400 1000` 同时导出两档。独立的 `enhance-vsr` 输出标准动态范围 JPEG。

```powershell
hdrview convert-vivo ".\images\vivo-photos" -o ".\results\vivo" --target-nits 400 1000
hdrview verify ".\results\vivo" --json ".\results\verification.json"
```

## 文档

- [vivo 工作流](docs/workflows/vivo-reconstruction.md)涵盖样本兼容性、结构诊断和重建参数。vivo 输出是研究性高光重建，手机相册的极致动态范围观感仍待验证。
- [NVIDIA 工作流](docs/workflows/nvidia-truehdr.md)涵盖环境安装、TrueHDR 参数、放大与去噪，以及已有中间结果的批量转换。
- [验证记录](docs/verification.md)涵盖格式、参考解码和 Windows 显示验收。文件回读通过后，屏幕显示效果仍可用兼容显示器手动核验。
- [项目结构](docs/structure.md)、[原生组件构建](src/hdrview/native/README.md)和[上游来源](docs/research/source-audit.md)供开发者参考。编码使用 Google 的 libultrahdr 和 libjpeg-turbo，模型增强调用 NVIDIA 官方软件包。

安装测试依赖后，在仓库根目录执行测试。部分集成测试使用 [本地样本](docs/samples.md)和已构建的原生工具。

```powershell
python -m pip install -e ".[test]"
python -m pytest
```

## 许可证

本项目原创代码和文档采用[零条款 BSD 许可证](LICENSE)（`0BSD`）。第三方依赖、原生库与模型适用各自的许可证。详见[上游来源](docs/research/source-audit.md)。
