# 项目结构与调用链

`src/hdrview/__main__.py` 提供 `python -m hdrview` 入口，`cli.py` 负责命令参数解析与流程编排。安装 Python 包后也可使用 `hdrview` 命令，原有 `python -m hdrview.cli` 继续可用。三种调用方式使用同一解析入口。vivo 路线由 `vivo/` 解析和重建辅助图，NVIDIA 路线由 `nvidia/` 执行模型及前后处理；两条路线分别生成共享的线性 BT.2020、203 尼特参考白中间表示。

`nvidia/vsr.py` 封装官方视频超分辨率增强：`enhance-vsr` 单独生成标准 sRGB JPEG 与报告，`enhance-nvidia --vsr` 先增强再执行 TrueHDR。增强产生的派生基础图与原图分开保存；报告记录原图哈希、尺寸、实际增强参数和派生图哈希。读取经过增强的 TrueHDR 中间结果时，`convert-nvidia` 使用 `--sdr-base` 指定并校验对应派生 JPEG。

转换流程由命令入口调用对应路线，再由 `output/export.py` 的 `export_hdr` 统一组织导出。`mapping.py` 负责共享高光映射，`output/ultrahdr.py` 和 `output/jxr.py` 分别负责对应格式编码，`native/` 包含原生编码桥接及构建脚本。默认目标为 1000 尼特；选择 400 尼特时，同一映射结果用于两种输出格式。

```text
src/hdrview/
├─ __main__.py、cli.py       命令入口及编排
├─ nvidia/
│  ├─ preprocess.py         共享输入色彩转换
│  ├─ vsr.py                可选放大、去噪、去模糊
│  ├─ runtime.py            TrueHDR 模型与输出转换
│  ├─ postprocess.py        中间结果来源校验
│  └─ provenance.py         复用结果的报告追溯
├─ vivo/                    手机辅助高光解析与候选重建
├─ io/                      源文件、目录枚举、中间结果和输出目录
├─ color/、mapping.py       色彩处理和目标亮度映射
├─ output/                  两条管线的共享编码出口
├─ native/                  C++ 桥接与唯一构建入口
└─ verify/                  结构检查和参考解码
```

调用链为：原图 → 色彩转换 → 可选视频超分辨率 → TrueHDR → 共享导出。独立 `enhance-vsr` 在生成派生基础 JPEG 后结束。复用中间结果的 `convert-nvidia` 直接进入来源校验与共享导出，报告中的 `intermediate_input` 记录两份输入中间文件的绝对路径与各自哈希；`vsr.executed=false` 表示本轮未重新执行模型，已有增强参数仍会保留。

- `color/`：色域、传递函数和颜色配置转换。
- `io/`：源文件、输出目录和中间结果读写。`inputs.py` 统一识别 JPEG 扩展名，`intermediate.py` 统一中间文件命名，保留照片名称中的点号。
- `verify/`：结构、回读和比较验证。
- `tests/`：单元测试、集成测试和测试数据生成工具。
- `docs/` 保存工作流、研究、验证和[样本说明](samples.md)。历史设计与实施计划集中在 [`docs/history/`](history/)。
- `images/` 存放被 Git 忽略的本地图片数据。
- `output/` 是默认输出根目录。命令在当前工作目录下创建 `output/vivo` 或 `output/nvidia`，将一批图片的产物和逐图报告直接写入对应目录。

批量命令在系统临时目录逐张处理，整批编码成功后再发布。`io/output.py` 检查目录与文件冲突，通过独占创建保护已有结果，发布失败时清理本次已写入的文件。

项目源码与运行环境、图片数据及生成结果分开存放。`.venv` 可用于通用开发和测试，`.venv-nvidia` 用于 NVIDIA 依赖；环境需自行准备，项目不会自动创建或安装依赖。原生构建入口保留在 `src/hdrview/native/Build-Native.ps1`。历史设计记录描述当时的方案，当前使用方式以 [项目说明](../README.md) 和工作流文档为准。
