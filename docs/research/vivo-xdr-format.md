# vivo 私有 XDR 格式研究记录

## 已实测结构（2026-11-16）

当前四张 Neo9 Pro 样本采用以下布局，而非 Android Ultra HDR 的 MPF 第二图布局：

```text
主 JPEG（4096×3072）
  └─ EOI
streamdata                    # 实测无 NUL 结尾
  └─ 辅助 JPEG（2048×1536，Display-P3）
streaminfo\0
  ├─ 尚未解释的固定/可变头部字节
  ├─ streamcount\0 01 vivo
  ├─ vivo{UTF-8 JSON}\0       # 包含 com.vivo.xdr.maxGain
  └─ 其他未解释的 trailer 字段
```

辅助 JPEG 自身的 EOI 决定其长度，streaminfo 从辅助 EOI 后开始。不能使用整文件最后一个 `FFD9` 作为主图结束，因为私有尾部也可能出现这些字节；也不能全文件搜索 `FFD8` 寻找辅助图，因为 EXIF 缩略图也包含 JPEG。

## 证据边界

- `HDRImage` 在 ExifTool 中仅被描述为“highlights of HDR image”。
- 文件包含私有高光辅助图不等于标准 Ultra HDR，也不保证相册一定点亮 HDR。
- `com.vivo.xdr.maxGain` 不直接等同曝光倍数或标准 `GainMapMax`。
- 样本未发现 `hdrgm`、`GContainer`、MPF、ISO 21496-1 URN、`GAINMAPDATA/Gainmapinfo`。
- 首版白名单只接受四张样本对应的 Neo9 Pro 当前结构。其它机型、系统、尺寸、ICC 或模式一律显示未验证/不支持。

## 后续待研究

- 辅助图的传递函数、实际光强单位、是否经过遮罩/局部滤波。
- 主辅图在几何与色彩上的精确对应。
- 手机相册额外的显示端处理。没有受控手机参考时，只能交付“合理 HDR 重建，手机 XDR 观感未验证”。
