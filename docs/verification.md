# 验证记录

## 2026-11-17：标准 Ultra HDR 垂直切片

已在本机使用官方 `libultrahdr v2.0.2`（提交 `e5f5a022…`）与固定 `libjpeg-turbo 3.2.0` 构建 Windows x64 桥接。64×64 合成图的 SDR 基础为 64/255 灰阶，中央 16×16 区域的线性 HDR 为 SDR 的 4 倍。

- 官方 `is_uhdr_image` 确认主图、增益图与元数据完整；容器含 MPF 与 ISO/XMP，不能只检查 XMP 标签。
- API-3 会重排容器 marker；像素和 ICC 另行核验，原 JPEG 字节不必原样出现在输出中。
- `display_boost=1` 得到 SDR；完整 HDR 容量解码恢复高光。编码同时写 ISO 21496-1 与 XMP，既有用户 Luma 验收已能识别原生 HDR；此前仅 ISO 不能识别。

当前结果只证明标准编码与参考解码，不证明 vivo 公式正确或复现手机 XDR 观感。

## 2026-11-17：高光映射与 Windows JPEG XR

- vivo 连续融合、共享 HDR400 有理映射及超高峰值/暗部测试已执行。HDR400 只映射一次，JPEG 和 JPEG XR 共用映射内容；HDR1000 保留原内容。
- Windows WIC 原生 `GUID_WICPixelFormat64bppRGBAHalf` 编解码已执行；尺寸、有限值、颜色、高光及防覆盖有集成测试。Rec.709/BT.2020 使用数值逆矩阵，scRGB 参考白 80 尼特。
- 单张真实 4096×3072 vivo 样本已写入主仓库新的 `output/vivo/run-006`。JPEG XR 编码后以 WIC 回读成功；官方 JPEG 报告容量分别为 400/203（1.97044）与 1000/203（4.92611），原图 SHA-256 保持 `2124089e036e82be33924a0724ec0e3901069ea558e4080949975919c54c41fc`。
- 新样本仍标记“合理 HDR 重建，手机 XDR 观感未验证”；`windows_photos_hdr_verified=false`。Windows Photos、Luma 显示和其他查看器仍需手动验收，不能把 WIC 回读或能打开当成显示证明。

## 2026-11-17：NVIDIA 边界与自动化

`enhance-nvidia` 使用官方 `nvvfx.TrueHDR`，无 ComfyUI。合成替代接口测试覆盖参数、固定版本及元数据回退、输出 H×W/`uint32` 校验、PQ/RGB10A2、CUDA 检查、运行顺序、模型释放、原图绑定、中间结果持久化与导出；缺依赖时输出目录不创建。

**本机真实 NVIDIA 已执行**：在项目根目录隔离 `.venv-nvidia` 安装 PyTorch 2.11.0+cu128 与 nvidia-vfx 0.2.0.0，CUDA 可用，GPU 为 RTX 4070 Laptop，驱动 617.14。`output/nvidia/run-001` 由真实 TrueHDR 模型处理原始夜景 `IMG_20261116_212648.jpg` 生成；报告 `gpu_executed=true`，默认参数为对比度 100、饱和度 100、中灰 50、目标 1000 尼特、开启去色带，实际内容容量为 4.920855。4096×3072 的 Ultra HDR JPEG 和 JPEG XR 均已验证/回读，且保存可复用的线性 HDR 中间文件。

真实调试发现：显式创建并切换非默认 CUDA 流会使该版本 SDK 报初始化错误（代码 -12）；官方默认流最小测试成功。项目固定使用默认流 `stream_ptr=0`。PyTorch 2.11 CUDA 的 `uint32` 不支持按位运算，RGB10A2 改为先复制到主机、再用 NumPy 解包。这些是真实运行验证的兼容性修正，不是算法效果证明。

NVIDIA 的 AI 视觉改善、区域边缘和亮部细节仍待用户与 vivo `run-006` 对照，不因 GPU 成功就宣称观感达标。

最终完整测试命令：`.venv\Scripts\python.exe -m pytest -q`，最终审查修正后实际 **122 passed**，无跳过、无失败，耗时 94.20 秒。此前基线为 118 passed；本轮新增测试先观察到错误尺寸/数据类型被接受、版本元数据未回退、实际容量与中间文件缺失、JPEG XR 哈希字段未改名等失败，修正后相关 NVIDIA/JPEG XR 范围 **39 passed**。`verify --json` 的数组序列化回归测试也由失败转为通过。合成 NVIDIA 中间结果与替代模型只验证契约，不是模型证据。可选 10-bit AVIF PQ 未做编码或显示实测，不是默认输出。
