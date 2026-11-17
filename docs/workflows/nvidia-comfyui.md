# NVIDIA TrueHDR 到标准 Ultra HDR

## 边界

- 真实 NVIDIA 推理由独立 ComfyUI 环境执行，使用官方 `RTXTrueHDR`。
- 原始主图先经 ICC 处理为 sRGB，再由自定义节点满足 Rec.709 gamma 2.2 输入。
- 输出保留 BT.2020/PQ，转共享线性 BT.2020 中间结果。
- `convert-nvidia` 校验原图 SHA-256、尺寸和 `pipeline=nvidia-truehdr`，然后把原始 SDR JPEG 与 HDR 中间结果交给官方 libultrahdr。
- ComfyUI 核心不直接写 Ultra HDR；Luma 只用于查看和对照，不用截图导出。

## 当前验证

已通过合成 NVIDIA 声明中间结果的编码、哈希拒绝、尺寸和 Ultra HDR 结构测试。当前核心环境未安装 PyTorch/nvvfx，真实 GPU 集成测试明确跳过，不能声称 AI 已实测。

## 后续真实执行

安装与执行前先确认 ComfyUI、PyTorch、NVIDIA wheel 的来源、版本和独立环境。完成后用 400/650 nit 各生成一份中间结果，并执行：

```powershell
python -m hdrview.cli convert-nvidia <原始 JPEG> --intermediate <中间结果 stem> --output <新目录>
```

输出的 Ultra HDR 应被 Luma 识别为原生 HDR，不叠加第二次 RTX 增强。Windows Photos 与其他查看器只按实测记录，不预设支持。

## AVIF 诊断输出

可选 10-bit AVIF PQ 用于独立检查 HDR 中间结果；它不是 Ultra HDR，也不自动具备完整 HDR10 主控显示器/内容亮度元数据。当前核心环境没有 PyAV/SVT-AV1，未进行 AVIF 编码实测。
