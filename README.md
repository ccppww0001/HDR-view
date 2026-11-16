# HDR-view：vivo XDR 与 NVIDIA 双管线研究工具

本项目探索两条独立的 HDR 路线：

1. 使用 iQOO Neo9 Pro 原始 JPEG 中的 vivo 私有高光辅助信息，构建合理的 HDR 重建。
2. 使用 ComfyUI NVIDIA TrueHDR 对 SDR 主图进行 AI 增强。

两条路线计划共享官方 `libultrahdr` 编码器，输出普通 SDR 基础图和标准 Ultra HDR 增益图。

## 当前状态

**项目处于初始骨架阶段，尚不能执行 HDR 转换。** 当前仅实现只读源文件快照、SHA-256 校验和防覆盖输出目录。项目版本 `0.0.0` 表示尚未发布任何转换能力。

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
