# HDR 色彩管线约定

## 输入

原始主图与 vivo 辅助图分别读取嵌入 ICC。Pillow 的 `convert("RGB")` 不应用 Display-P3 ICC，因此项目使用 Pillow ImageCms（LittleCMS）将其转换到标准 sRGB，不能仅丢弃 ICC 后把数值当 sRGB。

## 中间表示

- 像素计算：float32，RGBA，alpha=1。
- 落盘：RGBA float16 + JSON sidecar，拒绝 NaN、Infinity 和超过 65504 的值。色域矩阵舍入可产生极小负分量，`_validate` 仅允许不小于 -0.01 的容差，低于该阈值即拒绝；这不是允许真实负亮度。
- 色度：BT.2020；传递函数：linear。
- SDR 参考白：203 nit。`1.0` 表示相对该参考白的线性光单位，不表示某台 HDR400 的峰值。
- `hdr_capacity_max` 是相对 SDR 的倍率，不是标准元数据字段，也不等于显示器的 nit 上限。Ultra HDR HDR400 和 HDR1000 的实际容量分别为 `400/203≈1.97044` 和 `1000/203≈4.92611`；HDR400 编码前只对高光应用一次有理压缩映射，HDR1000 保留原内容。

## NVIDIA 接口

NVIDIA TrueHDR Python API 要求 Rec.709/D65、gamma 2.2。流程是 Display-P3 ICC → sRGB → sRGB 逆传递函数 → gamma 2.2。官方输出是 BT.2020/PQ；本项目将 PQ 转为绝对亮度，再除以 203 得到共享线性单位。HLG 不作为首选中间格式。

## Ultra HDR 输出

HDR 重建与 SDR 主图共同交给官方 libultrahdr API-3，增益由实际重建关系计算。不能将 vivo `maxGain` 直接复制成标准 `GainMapMax`。不支持 HDR 的查看器仍应看到普通 SDR 基础图。

## Windows JPEG XR

HDR400 映射后的 BT.2020/203-nit 线性像素乘以 `203/80`，再用 Rec.709→BT.2020 矩阵的**数值逆矩阵**转到 Rec.709 scRGB/80-nit，编码为 WIC `GUID_WICPixelFormat64bppRGBAHalf`。矩阵不是正交矩阵，不能用转置代替逆矩阵；原生回读使用正向矩阵和 `80/203` 返回共享模型。

JPEG XR 固定 scRGB 容量字段不表示绝对物理显示上限。WIC 浮点解码及内容峰值证明数值保留，不证明 Windows Photos HDR 显示已经验收。JPEG XR 与 PQ AVIF 不同，也不自动携带 HDR10 主控元数据。
