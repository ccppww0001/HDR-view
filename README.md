# HDR-view

HDR-view 是一个面向 Windows 的批量照片处理工具，提供 vivo 私有辅助图识别与高光重建，以及 NVIDIA TrueHDR 照片增强。两条路线均可导出 Ultra HDR JPEG。

## Windows 单文件版

[下载 HDR-view.exe](https://github.com/ccppww0001/HDR-view/releases/latest/download/HDR-view.exe)。在可执行文件所在目录打开 PowerShell，输入照片文件或目录即可转换。

```powershell
.\HDR-view.exe --help
.\HDR-view.exe convert-vivo "D:\照片"
.\HDR-view.exe verify ".\output\vivo"
```

单文件版内置 Python 和原生编码组件。NVIDIA 模型使用单独安装的运行环境，配置和打包步骤见 [Windows 发行版](docs/windows-release.md)。

## 从源码运行

使用 64 位 Windows、PowerShell 7、Python 3.12，以及 Visual Studio 的「使用 C++ 的桌面开发」工作负载（含 CMake）。在仓库根目录执行以下命令。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
.\src\hdrview\native\Build-Native.ps1 -ToolDirectory (Join-Path (Get-Location) '.tools') -Test
hdrview --help
```

完成 [NVIDIA 环境安装](docs/workflows/nvidia-truehdr.md#安装环境)后，可用同一命令入口运行 TrueHDR、放大、去噪和去模糊。

## 输入与输出

输入支持单个或多个 JPEG 文件、目录及其组合。目录读取当前层的 `.jpg` 和 `.jpeg`，扩展名大小写均可。含空格的路径请加引号。

| 功能 | 命令 | 默认目录 |
| --- | --- | --- |
| vivo 高光重建并导出[^vivo-reference] | `convert-vivo` | `output/vivo` |
| 保存 vivo 重建中间结果 | `reconstruct-vivo` | `output/vivo` |
| NVIDIA TrueHDR 增强并导出 | `enhance-nvidia` | `output/nvidia` |
| 复用 NVIDIA 中间结果导出 | `convert-nvidia` | `output/nvidia` |
| NVIDIA 照片放大、去噪或去模糊 | `enhance-vsr` | `output/nvidia` |

默认路径相对于命令的运行目录。`-o`、`--output-dir` 和 `--output` 均可指定输出目录。图片、中间文件和逐图报告平铺存放，报告命名为 `原图名-命令名-report.json`。

同批照片使用不同的文件主名。重跑同一张照片时，可通过 `-o` 将结果保存到另一目录。命令会报告同名冲突，整批编码成功后再写入目标目录。vivo 批处理会列出并跳过普通照片，遇到损坏或超出支持范围的辅助图结构时会报出对应文件。

转换默认输出 1000 尼特 Ultra HDR JPEG。选择 `--target-nits 400` 时输出 400 尼特 Ultra HDR JPEG 和浮点 JPEG XR，选择 `--target-nits 400 1000` 时同时导出两档。独立的 `enhance-vsr` 输出标准动态范围 JPEG。

```powershell
hdrview convert-vivo ".\images\vivo-photos" -o ".\results\vivo" --target-nits 400 1000
hdrview enhance-nvidia ".\images\photos" -o ".\results\nvidia"
hdrview verify ".\results\vivo" --json ".\results\verification.json"
```

## 文档

| 内容 | 入口 |
| --- | --- |
| vivo 样本、格式检查和高光重建参数 | [vivo 工作流](docs/workflows/vivo-reconstruction.md) |
| NVIDIA 环境、增强参数和中间结果复用 | [NVIDIA 工作流](docs/workflows/nvidia-truehdr.md) |
| 样本来源、格式检查和参考解码结果 | [验证记录](docs/verification.md) |
| 源码结构、原生构建和参考来源 | [项目结构](docs/structure.md) · [原生组件构建](src/hdrview/native/README.md) · [上游来源](docs/research/source-audit.md) |

## 测试

在仓库根目录安装测试依赖并运行测试。集成测试使用已构建的原生组件，样本用例读取[本地照片](docs/samples.md)。

```powershell
python -m pip install -e ".[test]"
python -m pytest
```

## 许可证

当前源码和文档采用 [MIT 许可证](LICENSE)。使用、修改和分发时，保留版权声明和许可文本。各发行包以随包附带的许可证为准。第三方依赖、原生库与模型适用各自的许可证，见[上游来源](docs/research/source-audit.md)。

[^vivo-reference]: vivo 私有辅助图的识别规则参考了 iQOO Neo9 Pro 样张。
