# 项目结构与调用链

安装 Python 包后可通过 `hdrview`、`python -m hdrview` 或 `python -m hdrview.cli` 调用同一套命令。Windows 单文件版由 `release.py` 启动，可通过指定解释器调用独立的 NVIDIA 环境。

## 转换流程

| 功能 | 处理步骤 |
| --- | --- |
| vivo 高光重建 | 解析主图和私有辅助图 → 重建高光 → 导出 |
| NVIDIA TrueHDR | 读取照片 → 转换输入色彩 → 可选放大、去噪或去模糊 → TrueHDR → 导出 |
| NVIDIA 照片增强 | 读取照片 → 放大、去噪或去模糊 → 生成标准动态范围 JPEG 和报告 |
| NVIDIA 中间结果复用 | 校验原图和中间结果的来源 → 校验派生基础图（如有）→ 导出 |

vivo 重建和 NVIDIA TrueHDR 都使用线性 BT.2020、203 尼特参考白作为中间表示。`output/export.py` 统一组织导出。`mapping.py` 负责 400 尼特高光映射，Ultra HDR JPEG 和浮点 JPEG XR 共用映射结果。1000 尼特为默认导出目标。

```text
src/hdrview/
├─ __main__.py、cli.py       命令入口及批处理
├─ release.py               Windows 单文件版入口
├─ vivo/                    私有辅助图识别与高光重建
├─ nvidia/                  模型运行、色彩转换及来源校验
├─ io/                      源文件、目录输入、中间结果和输出
├─ color/、mapping.py       色彩处理与目标亮度映射
├─ output/                  共享编码出口
├─ native/                  C++ 编码组件与构建脚本
└─ verify/                  结构检查和参考解码
```

## 文件与报告

- `io/inputs.py` 负责目录中的 JPEG 枚举，`io/intermediate.py` 统一中间结果命名并保留照片名称中的点号。
- 批量命令逐张编码到系统临时目录。整批完成后，`io/output.py` 通过独占创建将产物写入目标目录。写入异常时清理本批已发布的文件。
- `convert-nvidia` 通过 `intermediate_input` 记录两份中间文件的绝对路径与哈希。派生基础图按文件名匹配，也可通过 `--sdr-base` 指定。重编码报告保留已记录的增强参数。
- `images/` 存放本地样本。`output/vivo` 和 `output/nvidia` 是当前工作目录下的默认结果位置，批次中的图片、辅助文件和报告直接写入对应目录。

## 开发目录

`.venv` 用于通用开发和测试，`.venv-nvidia` 用于 NVIDIA 模型依赖。原生构建入口为 `src/hdrview/native/Build-Native.ps1`，单文件打包入口为 `scripts/build-release.py`。

`tests/` 保存单元测试、集成测试及测试数据生成工具。`docs/` 保存工作流、研究和验证记录，早期设计与计划集中在 [历史记录](history/)。
