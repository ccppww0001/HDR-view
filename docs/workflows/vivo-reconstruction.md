# vivo 辅助高光重建

识别规则参考了 iQOO Neo9 Pro 的样张。`vivo` 是这些样张写入文件的私有格式标识。样本结构、原图记录和兼容范围见[样本说明](../samples.md)。

## 检查与转换

```powershell
hdrview inspect ".\images\fromthephone"
hdrview analyze-vivo ".\images\vivo-photos"
hdrview convert-vivo ".\images\vivo-photos"
hdrview reconstruct-vivo ".\images\vivo-photos" -o ".\results\intermediate"
```

| 命令 | 结果 |
| --- | --- |
| `inspect` | JPEG 结构、原图哈希、辅助图偏移和私有 `maxGain` 观测值 |
| `analyze-vivo` | 主图和辅助图的亮度关系、亮区位置及覆盖范围，普通照片会记录对应状态 |
| `convert-vivo` | Ultra HDR JPEG 和逐图报告，选择 400 尼特时同时输出浮点 JPEG XR |
| `reconstruct-vivo` | `原图名-vivo.f16rgba`、配套的 `原图名-vivo.json` 和逐图报告 |

检查和分析命令默认在终端显示报告，`--output report.json` 可将报告保存为文件。两条重建命令均支持多个文件和目录，默认直接写入当前目录下的 `output/vivo`。批处理会列出并跳过普通照片。单张转换要求输入含私有辅助图，解析异常或超出兼容范围时会报出对应文件。

## 重建与导出参数

默认重建模型为 `additive-residual`，默认参数为 `--scale 4.0 --max-gain-cap 4.5 --highlight-threshold 0.02`。这些参数用于候选高光重建，计算原理见[重建研究](../research/vivo-reconstruction.md)。

`convert-vivo` 默认导出 1000 尼特。指定 `--target-nits 400` 可生成 400 尼特 Ultra HDR JPEG 和浮点 JPEG XR，指定 `--target-nits 400 1000` 可导出两档。报告字段 `xdr_appearance_verified` 用于标记手机相册对照验收状态。文件结构与参考解码结果见[验证记录](../verification.md)。
