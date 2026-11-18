# 验证记录

## 2026-11-18 Windows 单文件发行版

从独立临时目录运行 `HDR-view.exe`，搜索路径仅包含 Windows 系统目录。两张样张通过含中文和空格的路径批量导出 400 尼特与 1000 尼特 Ultra HDR JPEG、浮点 JPEG XR 和逐图报告。四张 Ultra HDR JPEG 均通过参考解码，原图哈希保持一致。

同一可执行文件通过独立 NVIDIA 环境运行去噪与 TrueHDR。重编码测试直接读取已有中间结果。`--licenses` 可读取随包提供的许可文本。[Windows 发行版](windows-release.md)

## 2026-11-18 批量输出与样本复核

当天的 22 张照片中，17 张含辅助图，在 `output/vivo` 平铺生成 Ultra HDR JPEG 和逐图报告。其余 5 张只含相机元数据，命令逐张列出并跳过。包含 `maxGain=0.6358773` 的样张通过编码与参考解码，22 张原图哈希保持一致。[样本与色彩分析](research/vivo-xdr-format.md#2026-11-18-照片复核)

NVIDIA 路线用两张测试图实际运行去噪与 TrueHDR，核对 `output/nvidia`、报告路径及混合目录的参考解码。重编码按目录匹配中间文件和派生基础图，在指定目录导出 400 尼特 Ultra HDR JPEG 与浮点 JPEG XR。

测试套件通过 165 项。另 4 项依赖两张早期私人样张，由测试工具记为跳过。测试临时目录在完成后清理。

## 2026-11-17 视频超分辨率与输入输出

在 NVIDIA GeForce RTX 4070 Laptop 显卡上运行缩小照片的放大、去噪和去模糊，完整照片的 4096×3072 → 8192×6144 放大，以及完整照片去噪后执行 TrueHDR。TrueHDR 导出了 1000 尼特 Ultra HDR。历史本地结果位于 `output/IMG_20261116_204341/vsr-upscale/run-001` 和 `output/IMG_20261116_204341/nvidia-vsr-denoise/run-001`。

本轮覆盖带点文件名、大写 JPEG 扩展名、目标亮度去重，以及复用结果时的增强参数和文件哈希。用缩小样张实测了 2 倍放大、TrueHDR、1000 尼特导出、按中间像素路径重编码和参考解码。报告保留可从历史中间文件读取的来源字段。

在 `.venv-nvidia` 中设置 `PYTHONPATH=src` 和 `PYTHONUTF8=1`，执行 `python -B -m pytest -q -p no:cacheprovider --basetemp=output/.release-review-tests`。全部 163 项通过，用时 74.24 秒，上一轮通过 160 项。命令入口同时覆盖 `python -m hdrview` 和原有入口。测试目录与缩小样本在完成后清理。

## 2026-11-17 目标亮度与共享导出

默认目标统一为 1000 尼特，400 尼特和双档输出由 `--target-nits` 选择。共享导出集中在 `src/hdrview/output/export.py`，覆盖命令入口、亮度选择和参考解码。五张样张通过辅助图解析与原图哈希检查，单个填充零字节按原始偏移读取。[项目结构](structure.md)

在 `.venv-nvidia` 中设置 `PYTHONPATH=src` 和 `PYTHONUTF8=1`，执行 `python -B -m pytest -q -p no:cacheprovider --basetemp=output/.structure-check-tests`。通过 123 项，目录联接用例依赖 Windows 创建权限，由测试工具记为跳过。测试临时目录在完成后清理。

## 2026-11-17 Ultra HDR 容器与回读

用 Google libultrahdr 2.0.2 和 libjpeg-turbo 3.2.0 构建 Windows 编码组件。64×64 合成图的标准动态范围底图为 64/255 灰阶，中央 16×16 区域的线性高动态范围亮度为底图的 4 倍。组件版本与来源见[原生组件构建](../src/hdrview/native/README.md)。

- 使用 `is_uhdr_image` 核对底图、增益图和元数据，并检查多图容器以及 ISO 21496-1 和 XMP 两份标记。
- 官方编码接口会重排容器标记。底图以像素、嵌入色彩配置和结构完整性验收。
- 以 `display_boost=1` 解码得到标准动态范围底图，以完整容量解码恢复测试高光。Luma 样本验收识别了同时写入 ISO 21496-1 和 XMP 的文件。

## 2026-11-17 高光映射与 Windows JPEG XR

- 连续融合与高光映射用例覆盖极亮区域和暗部。400 尼特档采用一次有理映射，为 Ultra HDR JPEG 和浮点 JPEG XR 提供同一结果。1000 尼特档保留重建亮度关系。
- Windows Imaging Component 使用 `GUID_WICPixelFormat64bppRGBAHalf` 编码并回读。集成测试覆盖尺寸、有限值、颜色、高光和同名冲突。Rec.709 与 BT.2020 之间使用数值逆矩阵，scRGB 参考白为 80 尼特。
- 4096×3072 样张的历史结果位于 `output/vivo/run-006`。JPEG XR 通过浮点回读。两档 Ultra HDR JPEG 的容量分别为 `400/203≈1.97044` 和 `1000/203≈4.92611`。原图哈希为 `2124089e036e82be33924a0724ec0e3901069ea558e4080949975919c54c41fc`。

本组记录覆盖文件结构、原生回读和数值关系。手机相册、Windows 照片应用和其他查看器的显示效果以同一设备和显示条件下的实机对照为准。

## 2026-11-17 NVIDIA TrueHDR

官方 `nvvfx.TrueHDR` 在独立 `.venv-nvidia` 环境运行，使用 PyTorch 2.11.0 的 CUDA 12.8 构建、NVIDIA 视频效果软件包 0.2.0.0、RTX 4070 Laptop 显卡及 617.14 驱动。输入为夜景样张 `IMG_20261116_212648.jpg`，历史结果位于 `output/nvidia/run-001`。报告记录 `gpu_executed=true`、对比度 100、饱和度 100、中灰 50、目标 1000 尼特和启用去色带，测得内容容量为 4.920855。4096×3072 的 Ultra HDR JPEG 与 JPEG XR 通过回读，并保存了可复用的线性中间文件。

运行时采用官方默认计算流 `stream_ptr=0`。调试中切换独立计算流触发了初始化错误 `-12`。RGB10A2 输出先复制到主机，再通过 NumPy 对无符号 32 位整数解包。替代接口用例覆盖参数、版本元数据回退、尺寸和数据类型检查、模型释放、原图哈希、中间文件及导出。实机视觉对照可比较区域边缘、高光细节和 vivo 路线的亮度关系。

使用 `.venv\Scripts\python.exe -m pytest -q` 通过全部 122 项，用时 94.20 秒。此前基线通过 118 项，修正后的 NVIDIA 与 JPEG XR 相关范围通过 39 项。`verify --json` 的像素数组序列化回归用例也通过。10 位 AVIF 保留为独立诊断入口，日常导出使用 Ultra HDR JPEG 和浮点 JPEG XR。
