# HDR-view：vivo XDR 与 NVIDIA 双管线研究工具

本项目探索两条独立的 HDR 路线：

1. 使用 iQOO Neo9 Pro 原始 JPEG 中的 vivo 私有高光辅助信息，构建合理的 HDR 重建。
2. 使用 ComfyUI NVIDIA TrueHDR 对 SDR 主图进行 AI 增强。

两条路线计划共享官方 `libultrahdr` 编码器，输出普通 SDR 基础图和标准 Ultra HDR 增益图。

## 当前状态

**当前处于研究实现阶段。** 已实现只读源文件快照、SHA-256 校验、防覆盖输出、Neo9 Pro 私有 trailer/JSON/辅助 JPEG 解析、Display-P3 ICC 色彩转换、线性 BT.2020 中间表示，以及官方 `libultrahdr` 的 Ultra HDR 编码/参考解码。

`convert-vivo` 当前输出的是**研究候选的合理 HDR 重建，手机 XDR 观感未验证**。NVIDIA/ComfyUI 管线尚未完成安装和真实执行；Luma 尚未进行本机 HDR 显示验收。项目版本 `0.0.0` 表示尚未发布稳定转换能力。

## 当前 vivo 研究用法

先完成固定依赖构建，再执行：

```powershell
$env:HDRVIEW_TOOL_DIR = 'C:\Users\N452\AppData\Local\Temp\opencode\hdrview-build'
pwsh -File scripts/Build-Native.ps1 -Test
python -m hdrview.cli convert-vivo <原始 Neo9 Pro JPEG> --output <新的临时输出目录>
```

输出目录中生成 `*-UltraHDR.jpg` 和 `report.json`。报告必须保留 `xdr_appearance_verified=false`；不要将默认候选参数理解为 vivo 官方算法参数。`inspect`、`analyze-vivo`、`reconstruct-vivo` 分别用于结构检查、主辅高光诊断和中间结果生成。

## 设计与计划

- [已批准设计](docs/superpowers/specs/2026-11-16-vivo-xdr-ultra-hdr-design.md)
- [实施计划](docs/superpowers/plans/2026-11-16-vivo-xdr-ultra-hdr.md)

## 重要边界

- 首版只研究当前 Neo9 Pro 样本结构，不承诺其他 vivo 机型。
- 无受控手机拍屏参考时，vivo 结果只能称为“合理 HDR 重建，手机 XDR 观感未验证”。
- 原始照片、安装包、生成结果和本地环境均不纳入 Git。
- 中间 HDR 使用线性光和显示无关元数据，不把 HDR400 的亮度上限写入数据。

## 本地验证环境

Python 3.12，依赖见 `pyproject.toml`。项目使用隔离的 `.venv`，不更改系统 Python。

```powershell
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -e '.[test]'
.venv\Scripts\python.exe -m pytest
```
