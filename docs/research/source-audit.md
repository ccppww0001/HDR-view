# 上游源码与当前实现边界

## Luma HDR Photo Viewer

固定版本 `v0.1.32`，提交 `881361c2a3002cd8bdefa4922fc8ae18eb2d0a28`。源码直接调用官方 NGX TrueHDR 和 VSR，输出 FP16 scRGB，由 Windows 显示系统映射到 HDR。应用层未发现照片上传或遥测客户端；主要写入是本地图库、缩略图、日志和用户主动触发的文件关联。主程序不提供 TrueHDR 图像导出 API，因此本项目只把它作为最终原生 HDR 查看对照，不以截图作为数据输出。

NVIDIA SDK、模型和运行库存在闭源边界；Luma 的构建不是完全可复现证明。当前尚未在本机安装/执行 Luma 的实际 HDR 验收。

## ComfyUI NVIDIA VFX Nodes

固定提交 `38d790ded00650681fa3645362efe28c8560cf40`，版本 0.2.1。节点直接调用 `nvvfx.TrueHDR`，官方输出 BT.2020/PQ RGB10A2；仓库代码短小，没有照片上传/遥测/子进程行为。实际依赖是 NVIDIA 官方私有索引中的二进制 wheel，模型随 wheel 提供，Python 版本、CUDA 和驱动必须匹配。

已核实的风险：普通 LoadImage 不应用 Display-P3 ICC；官方输入要求 Rec.709/D65 gamma 2.2；默认 HLG 与核心固定 1000-nit 参考存在不一致。本项目采用 PQ 路线，自定义预处理与保存节点，不修改官方节点源码。

## 当前 NVIDIA 状态

核心环境只有 NumPy/Pillow/OpenCV/pytest，不含 PyTorch 或 `nvvfx`。合成声明中间结果的编码与绑定测试通过，真实 GPU 集成明确跳过。不能把此结果称为 TrueHDR 实测。

## 编码底座

使用 Google 官方 libultrahdr v2.0.2（提交 `e5f5a022fe96fc4dc2ee35c19f733a50df807abe`），以及 libjpeg-turbo 3.2.0，均有固定来源与 SHA-256。桥接不实现私有 vivo 公式，只使用官方 API-3 从 HDR 中间结果与原始 SDR JPEG 生成标准 Ultra HDR。
