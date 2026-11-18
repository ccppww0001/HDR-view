# iQOO Neo9 Pro 辅助高光重建

已验证样本来自 iQOO Neo9 Pro。`vivo` 是设备写入文件的私有格式标识。批量重建时，没有私有辅助图的照片会被列出并跳过，存在但损坏或暂未支持的结构会结束该批次。单独转换一张没有辅助图的照片会报错。样本结构与隐私说明见[本地样本](../samples.md)。

```powershell
hdrview inspect ".\images\fromthephone"
hdrview analyze-vivo ".\images\vivo-photos"
hdrview convert-vivo ".\images\vivo-photos"
hdrview reconstruct-vivo ".\images\vivo-photos" -o ".\results\intermediate"
```

- `inspect` 检查 JPEG 结构、哈希、辅助图偏移及私有 `maxGain` 观测值。`analyze-vivo` 分析主图与辅助图的高光关系，并列出缺少辅助图的照片。两条命令默认将报告写到终端，可通过 `--output report.json` 保存为文件。
- `convert-vivo` 默认导出 1000 尼特 Ultra HDR JPEG。指定 `--target-nits 400` 时导出 400 尼特 Ultra HDR JPEG 和浮点 JPEG XR，指定 `--target-nits 400 1000` 同时输出两档。
- `reconstruct-vivo` 保存线性高动态范围像素和配套元数据，文件名为 `原图名-vivo.f16rgba` 和 `原图名-vivo.json`。

两条重建命令都支持多个文件和目录，省略 `-o` 时直接写入当前目录下的 `output/vivo`。每张图的报告随产物保存在同一目录。默认模型为 `additive-residual`，默认参数为 `--scale 4.0 --max-gain-cap 4.5 --highlight-threshold 0.02`。这些是研究参数，报告使用 `xdr_appearance_verified=false` 表明手机相册观感尚未验证。
