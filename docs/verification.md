# 验证记录

## 2026-11-17：标准 Ultra HDR 垂直切片

已在本机使用官方 `libultrahdr v2.0.2`（提交 `e5f5a022…`）与固定 `libjpeg-turbo 3.2.0` 构建 Windows x64 桥接。64×64 合成图的 SDR 基础为 64/255 灰阶，中央 16×16 区域的线性 HDR 为 SDR 的 4 倍。

验证结果：
- 官方 `is_uhdr_image` 确认主图、增益图与元数据完整。
- 容器含 MPF 与 ISO/XMP 相关结构；不是只检查一个 XMP 标签。
- 基础图可由 Pillow 作为普通 SDR JPEG 读取，颜色与原始压缩图在 1 个 8-bit 码值内一致。
- API-3 会重排/重写容器 marker，不保证原始 JPEG 文件字节在输出中原样出现；像素和 ICC 必须另行核验。
- 线性输入未指定峰值时，官方默认按 10000 nit 确定 HDR 容量，约 49.2611；这不是输入高光倍率。
- `display_boost=1` 得到 SDR；按文件完整 HDR 容量解码时，中央恢复到原始四倍高光的 12% 相对容差内，周边暗部相对稳定。
- 测试中的伪 `gainmap_max_override` provenance 不影响官方元数据，不能手工覆盖实际 HDR/SDR 关系。

当前结果只证明标准编码与参考解码，不证明任何 vivo 高光融合公式正确，也不证明已复现手机 XDR 观感。

## 2026-11-17：双管线实现状态

- vivo 结构/JSON/辅助图读取、候选高光重建与标准 Ultra HDR 输出已在本机四张样本上实际运行；输入 SHA-256 不变。
- 真实夜景样本输出通过官方 probe 与参考解码。该输出是研究候选，参数未标定，报告固定 `xdr_appearance_verified=false`。
- NVIDIA/ComfyUI 自定义节点、PQ 中间结果、原图绑定与编码路径已实现，但本机核心环境没有 PyTorch、nvvfx 或 ComfyUI，真实 GPU 集成未执行。
- 当前测试为 80 passed、2 skipped（缺少 PyTorch/nvvfx 的 GPU 测试明确跳过）；合成 NVIDIA 声明中间结果只用于验证编码契约，不是 NVIDIA AI 实测。
- 10-bit AVIF PQ 写入器存在，但当前无 PyAV/SVT-AV1，未做编码或显示实测。
- Windows Photos、Luma 与其他 HDR 查看器尚未做本机显示验收；不得将文件结构成功当作所有设备已验证。
- 测试中的固定值只验证当前实现/版本行为，不能把 vivo 候选公式推广到其它手机或系统版本。
