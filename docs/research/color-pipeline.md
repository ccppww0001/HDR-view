# HDR 色彩管线约定

## 输入

原始主图与 vivo 辅助图分别读取嵌入 ICC。Pillow 的 `convert("RGB")` 不应用 Display-P3 ICC，因此项目使用 Pillow ImageCms（LittleCMS）将其转换到标准 sRGB，不能仅丢弃 ICC 后把数值当 sRGB。

## 中间表示

- 像素计算：float32，RGBA，alpha=1。
- 落盘：RGBA float16 + JSON sidecar，拒绝 NaN、Infinity、负值和超过 65504 的值。
- 色度：BT.2020；传递函数：linear。
- SDR 参考白：203 nit。`1.0` 表示相对该参考白的线性光单位，不表示某台 HDR400 的峰值。
- `hdr_capacity_max` 是相对 SDR 的倍率，不是标准元数据字段，也不等于显示器的 nit 上限。

## NVIDIA 接口

NVIDIA TrueHDR Python API 要求 Rec.709/D65、gamma 2.2。流程是 Display-P3 ICC → sRGB → sRGB 逆传递函数 → gamma 2.2。官方输出是 BT.2020/PQ；本项目将 PQ 转为绝对亮度，再除以 203 得到共享线性单位。HLG 不作为首选中间格式。

## Ultra HDR 输出

HDR 重建与 SDR 主图共同交给官方 libultrahdr API-3，增益由实际重建关系计算。不能将 vivo `maxGain` 直接复制成标准 `GainMapMax`。不支持 HDR 的查看器仍应看到普通 SDR 基础图。
