# vivo 研究候选工作流

`reconstruct-vivo` 只生成带 sidecar 的 HDR 中间结果；`convert-vivo` 导出标准 Ultra HDR JPEG 与 HDR400 JPEG XR。所有生成结果默认进入项目 `output/<任务>/run-NNN`，不覆盖旧输出，不声称复现手机观感。

```powershell
python -m hdrview.cli inspect D:\MyProject\HDR-view\images\fromthephone
python -m hdrview.cli analyze-vivo D:\MyProject\HDR-view\images\fromthephone\IMG_20261116_212648.jpg
python -m hdrview.cli reconstruct-vivo D:\MyProject\HDR-view\images\fromthephone\IMG_20261116_212648.jpg --output <临时结果目录>
```

参数默认：`additive-residual`、scale=4.0、max_gain_cap=4.5、highlight_threshold=0.02。它们是待标定研究参数，不是 vivo 官方参数。输出报告固定 `xdr_appearance_verified=false`，原始文件只读且输出目录不复用。
