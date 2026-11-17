# 项目结构与调用链

`src/hdrview/cli.py` 负责命令参数解析与流程编排。vivo 路线由 `vivo/` 解析和重建辅助图，NVIDIA 路线由 `nvidia/` 执行模型及前后处理；两条路线分别生成共享的线性 BT.2020、203 尼特参考白中间表示。

`nvidia/vsr.py` 封装官方视频超分辨率增强：`enhance-vsr` 单独生成标准 sRGB JPEG 与报告，`enhance-nvidia --vsr` 先增强再执行 TrueHDR。增强产生的派生基础图与原图分开保存；报告记录原图哈希、尺寸、实际增强参数和派生图哈希。读取经过增强的 TrueHDR 中间结果时，`convert-nvidia` 使用 `--sdr-base` 指定并校验对应派生 JPEG。

转换流程由命令入口调用对应路线，再由 `output/export.py` 的 `export_hdr` 统一组织导出。`mapping.py` 负责共享高光映射，`output/ultrahdr.py` 和 `output/jxr.py` 分别负责对应格式编码，`native/` 包含原生编码桥接及构建脚本。默认目标为 1000 尼特；选择 400 尼特时，同一映射结果用于两种输出格式。

- `color/`：色域、传递函数和颜色配置转换。
- `io/`：源文件、输出目录和中间结果读写。
- `verify/`：结构、回读和比较验证。
- `tests/`：单元测试、集成测试和测试数据生成工具。
- `docs/`：工作流、研究、验证和历史设计记录。
- `samples/` 和 `images/`：样本说明和本地图片数据。
- `output/`：按任务与运行目录保存生成结果和报告，历史结果保留。

项目源码与运行环境、图片数据及生成结果分开存放。`.venv` 可用于通用开发和测试，`.venv-nvidia` 用于 NVIDIA 依赖；环境需自行准备，项目不会自动创建或安装依赖。原生构建入口保留在 `src/hdrview/native/Build-Native.ps1`。历史设计记录描述当时的方案，当前使用方式以 [项目说明](../README.md) 和工作流文档为准。
