# Windows 单文件发行版

`HDR-view.exe` 面向 64 位 Windows。可直接执行 `inspect`、`analyze-vivo`、`reconstruct-vivo`、`convert-vivo`、`convert-nvidia` 和 `verify`。生成图片的命令接受多个 JPEG 文件或目录，省略 `-o` 时按功能写入当前目录下的 `output/vivo` 或 `output/nvidia`。

```powershell
.\HDR-view.exe --help
.\HDR-view.exe convert-vivo "D:\照片" --target-nits 400 1000
.\HDR-view.exe verify ".\output\vivo"
```

## NVIDIA 模型

`enhance-nvidia` 和 `enhance-vsr` 使用单独安装的 NVIDIA 运行环境。已有兼容环境时，设置 `HDRVIEW_NVIDIA_PYTHON` 为其解释器的完整路径，然后沿用同一可执行文件。

```powershell
$env:HDRVIEW_NVIDIA_PYTHON = 'D:\环境\.venv-nvidia\Scripts\python.exe'
.\HDR-view.exe enhance-nvidia "D:\照片" -o ".\output\nvidia"
```

新建环境时，使用 64 位 Python 3.12，按 [NVIDIA 工作流](workflows/nvidia-truehdr.md#安装环境)安装模型依赖。仅使用单文件版本时，可将该流程中的 `python -m pip install -e .` 换为 `python -m pip install numpy Pillow opencv-python-headless`。

## 构建

在仓库根目录打开 PowerShell 7，准备 [README](../README.md#从源码运行)列出的 Python 与 C++ 构建环境，然后运行：

```powershell
python -m pip install -e ".[release]"
.\src\hdrview\native\Build-Native.ps1 -ToolDirectory (Join-Path (Get-Location) '.tools') -Test
python .\scripts\build-release.py
Get-FileHash .\dist\HDR-view.exe -Algorithm SHA256
```

脚本使用 PyInstaller 生成 `dist/HDR-view.exe`。构建输入包括项目源码和两个原生编码组件，以及对应许可证文本。在单文件版中运行 `HDR-view.exe --licenses` 可查看这些文本。
