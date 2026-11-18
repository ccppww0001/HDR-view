# Windows 单文件发行版

[下载 HDR-view.exe](https://github.com/ccppww0001/HDR-view/releases/latest/download/HDR-view.exe)。发行版面向 64 位 Windows，内置 Python 和两种原生编码组件。它可直接执行 JPEG 结构检查、vivo 辅助图诊断与转换、NVIDIA 中间结果重编码，以及输出验证。

```powershell
.\HDR-view.exe --help
.\HDR-view.exe convert-vivo "D:\照片" --target-nits 400 1000
.\HDR-view.exe verify ".\output\vivo"
```

生成图片的命令接受多个 JPEG 文件或目录。`-o` 指定输出目录。默认路径为当前运行目录下的 `output/vivo` 或 `output/nvidia`。

## NVIDIA 模型

`enhance-nvidia` 和 `enhance-vsr` 通过 `HDRVIEW_NVIDIA_PYTHON` 调用单独安装的 NVIDIA 环境。将变量设为该环境中 `python.exe` 的完整路径，即可从单文件版启动模型。

```powershell
$env:HDRVIEW_NVIDIA_PYTHON = 'D:\环境\.venv-nvidia\Scripts\python.exe'
.\HDR-view.exe enhance-nvidia "D:\照片" -o ".\output\nvidia"
```

新建环境时，使用 64 位 Python 3.12，在环境中安装 NumPy、Pillow、OpenCV、PyTorch 和 NVIDIA 视频效果包。单文件版内置项目代码，应用依赖使用 `python -m pip install numpy Pillow opencv-python-headless` 安装。模型依赖的版本及索引见 [NVIDIA 工作流](workflows/nvidia-truehdr.md#安装环境)。

## 构建

按 [README](../README.md#从源码运行)准备 Python 与 C++ 构建环境，然后在仓库根目录执行以下命令。

```powershell
python -m pip install -e ".[release]"
.\src\hdrview\native\Build-Native.ps1 -ToolDirectory (Join-Path (Get-Location) '.tools') -Test
python .\scripts\build-release.py
Get-FileHash .\dist\HDR-view.exe -Algorithm SHA256
```

构建脚本使用 PyInstaller，将项目源码、原生编码组件和许可证文本封装为 `dist/HDR-view.exe`。运行 `HDR-view.exe --licenses` 可查看随发行版提供的许可证。
