# vivo XDR 与 NVIDIA AI 到标准 Ultra HDR 的项目设计

- 日期：2026-11-16
- 状态：用户已于 2026-11-16 批准。详见[当时的实施计划](2026-11-16-vivo-xdr-ultra-hdr.md)。
- 当前项目：`D:\MyProject\HDR-view`，尚无产品代码，当前目录不是 Git 仓库
- 目标设备：iQOO Neo9 Pro / OriginOS；Windows 11；RTX 4070 Laptop（8 GiB）；HDR400 显示器

## 1. 目标与优先级

建立一套可验证的 Windows 照片 HDR 工具，包含两条互相独立的增强路线：

1. **vivo 路线（首要）**：解析原始 JPEG 的 `streaminfo`、`streamdata`、`HDRImage`、私有 JSON 与 `com.vivo.xdr.maxGain`，尽可能使用拍摄时保存的高光信息，复现 OriginOS 相册开启 XDR 时的观感，再编码为标准 Ultra HDR JPEG。
2. **NVIDIA 路线**：以原始 SDR 主图为输入，使用 Luma / ComfyUI NVIDIA VFX Nodes 对应的 TrueHDR 技术生成 HDR 图像，并通过相同的标准 Ultra HDR 编码出口保存。

两条路线必须共享色彩、编码与验证模块，不得把 vivo 原始高光图直接改名为标准增益图，也不得将 AI 推断称为恢复了原始 XDR 数据。

### 已确认的用户意图

- 第一优先级是复现手机相册开启 XDR 的观感。
- 输出必须是标准 Ultra HDR，使得支持它的设备可以按自身 HDR 余量重建相近观感。
- 普通/不支持 HDR 的查看器显示普通 SDR 基础图，不强制全设备亮度一致。
- 先完成 Python 命令行研究工具和可重复的 ComfyUI 工作流，不先制作图形界面。
- 当前无法提供手机 XDR 开/关的受控拍屏对照，首版验收接受“合理 HDR 重建，手机 XDR 观感未验证”，不阻塞标准格式与合理融合的实现。
- vivo 路线采用显示无关的 HDR 中间表示：保存相对高光关系、明确色彩空间与 HDR 容量，不锁死 400-nit 峰值；手机与 HDR400 分别做显示适配。
- 首版输入承诺限定为本机 Neo9 Pro、当前 OriginOS、已验证的样本结构；其他机型、系统版本、相机模式明确报告“未验证/不支持”，不套用猜测的融合公式。

### 非目标与反目标

- 不承诺 HDR400、手机 OLED 与其他 HDR 屏幕具有一致的绝对亮度或完全一致的观感。
- 不通过单纯提亮全图、增加全局对比度或饱和度冒充 XDR。
- 不修改原始照片，不覆盖用户文件。
- 不将 PQ AVIF、HDR10、Ultra HDR、vivo 私有 XDR 当成同一种格式。
- 不把“浮点数值大于 1”“显示器能显示 HDR”“导出文件带 HDR 编码”混为一谈。
- 不在未经验证时声称已复现 vivo 私有算法。

## 2. 已验证的事实与待研究假设

### 已有实证

四张样本的主图均为 4096×3072、8-bit JPEG、Display-P3 ICC；主 JPEG EOI 后有 vivo 私有 `streaminfo/streamdata`。私有 `HDRImage` 是可解码的 2048×1536 Display-P3 JPEG，呈现空间对齐的高光内容；私有 JSON 含 `com.vivo.xdr.maxGain`。未发现 `hdrgm`、`GContainer`、MPF、ISO 21496-1 URN 或专利中的 `GAINMAPDATA/Gainmapinfo`。

| 文件 | HDRImage 大小 | maxGain | 高光图亮度≥64/255 的像素 |
|---|---:|---:|---:|
| IMG_20261111_175548.jpg | 840856 B | 4.5 | 0.610% |
| IMG_20261111_175601.jpg | 870151 B | 4.5 | 3.149% |
| IMG_20261116_212648.jpg | 708062 B | 1.3358011 | 0.072% |
| IMG_20261116_212653.jpg | 708958 B | 1.5154562 | 0.075% |

结论：样本属于“含 vivo 私有 XDR 辅助图的 JPEG”，不是已证实的标准 Ultra HDR。相册是否点亮 HDR 与文件是否有辅助数据不能互相替代。

### 待证实的核心假设

1. `HDRImage` 是线性光、经某种传递函数编码的高光残差、曝光较短的辅助图、遮罩加权高光，还是多阶段数据中的某一种。
2. 它的像素是否与主图在几何上严格对齐；是否存在缩放、裁切、镜头畸变差异或方向差异。
3. `maxGain` 是全局增益上限、对数域参数、曝光倍率、显示目标，还是仅用于相册色调映射的提示。
4. vivo 的融合是否包含局部色调映射、空间滤波、暗部保护、颜色恢复、降噪或内容相关处理。
5. 能否用公开数据得到一个**逼近**相册观感的重建模型；如不能，应停在可解释、可比较的近似，不宣称逆向完成。

### 官方编码能力

Google libultrahdr 的 API-1 接受 HDR raw（P010、RGBA1010102、RGBA float16）和 SDR raw，生成增益图、压缩两路图像并输出标准 Ultra HDR。本项目选择它作为**唯一标准 Ultra HDR 编码底座**，不自行发明容器结构。解码端用同一库及独立查看器交叉验证。

## 3. 总体架构

```text
原始 JPEG（只读）
  ├─ vivo 私有段解析 → 辅助图/参数/几何与色彩检查 → 候选重建模型 → HDR 中间结果
  └─ ICC 正确的主图 → SDR 基础图 ───────────────────────────────┐
                                                               ├→ libultrahdr → Ultra HDR JPEG
NVIDIA TrueHDR → PQ/线性 HDR → 统一色彩转换 → HDR 中间结果 ───┘

共享：色彩管理、HDR 中间表示、元数据、验证、报告、回归测试
旁路：10-bit AVIF PQ（用于验证 HDR 中间结果，不替代 Ultra HDR）
```

项目采用 Python 3.12 作为研究和命令行主语言；HDR 像素计算使用 NumPy / OpenCV / 色彩管理库，NVIDIA 推理保留在官方 ComfyUI 节点或独立 NVIDIA Python 环境。libultrahdr 用官方 C++ 源码构建，通过很薄的本地命令行桥接或明确绑定的扩展调用；不假定官方提供 Python 接口。

## 4. 拟定项目结构

```text
HDR-view/
├─ pyproject.toml                 # 仅声明核心 Python 包与受控依赖
├─ README.md                      # 快速开始、能力边界、格式定义
├─ docs/
│  ├─ superpowers/specs/           # 已批准设计与后续实施计划
│  ├─ research/
│  │  ├─ vivo-xdr-format.md       # 字节结构、证据、未知项，不写猜测为事实
│  │  ├─ color-pipeline.md        # ICC、Rec.709、BT.2020、PQ、参考白
│  │  └─ source-audit.md          # 两个上游源码/版本/许可证/闭源边界
│  ├─ workflows/
│  │  ├─ vivo-reconstruction.md
│  │  └─ nvidia-comfyui.md
│  └─ verification.md             # 样本、版本、验收记录与已知失败
├─ src/hdrview/
│  ├─ cli.py                      # inspect / extract / reconstruct / enhance / encode / verify
│  ├─ model.py                    # ImageDocument、HdrImage、SdrImage、ColorState
│  ├─ io/
│  │  ├─ source.py                # 只读输入、SHA-256、输出防覆盖
│  │  └─ intermediate.py          # 浮点中间结果和机器可读色彩元数据
│  ├─ vivo/
│  │  ├─ container.py             # JPEG APP 段、EOI、streaminfo/streamdata 定位
│  │  ├─ metadata.py              # 私有 JSON、EXIF、参数类型与版本记录
│  │  ├─ auxiliary.py             # 辅助 JPEG 解码、方向、缩放、对齐诊断
│  │  └─ reconstruct.py           # 可插拔、明确编号的候选融合模型
│  ├─ color/
│  │  ├─ icc.py                   # Display-P3→Rec.709 等 ICC 正确转换
│  │  ├─ transfer.py              # sRGB/Rec.709 gamma 2.2/linear/PQ
│  │  └─ gamut.py                 # Rec.709、Display-P3、BT.2020 变换与 gamut 限制
│  ├─ nvidia/
│  │  ├─ preprocess.py            # 满足 NVIDIA Rec.709 gamma 2.2 输入契约
│  │  ├─ comfy_workflow.py        # 固定节点提交、参数和工作流生成/校验
│  │  └─ postprocess.py           # PQ 张量/16-bit 中间结果读回与统一转换
│  ├─ output/
│  │  ├─ ultrahdr.py              # 官方 libultrahdr 编码，不手写 MPF/XMP
│  │  ├─ avif.py                  # 10-bit AVIF PQ 诊断输出
│  │  └─ report.py                # 输入哈希、参数、环境、输出元数据
│  └─ verify/
│     ├─ structure.py             # 主图、MPF/XMP/ISO、增益图与元数据一致性
│     ├─ roundtrip.py             # SDR/HDR 解码、增益范围、色彩与几何验证
│     └─ compare.py               # 普通 SDR 对照、不同显示器余量、参考图比较
├─ comfyui/
│  ├─ workflows/nvidia_to_hdr.json
│  ├─ custom_nodes/hdrview_nodes/  # 仅在核心节点不足时增加，优先最少节点
│  └─ README.md                   # cu130+、Python、驱动、固定提交与安装说明
├─ native/
│  ├─ README.md                   # libultrahdr 固定提交、Windows 构建、许可证
│  └─ cmake/                      # 仅本地桥接的构建文件，不复制上游大项目
├─ tests/
│  ├─ fixtures/                   # 小型合成结构、损坏段、边界条件，不含私人原图
│  ├─ unit/                       # 二进制边界、色彩、参数与防覆盖
│  ├─ integration/                # 两条路线到 Ultra HDR 的端到端测试
│  └─ golden/                     # 公开/合成参考元数据与容差，不伪装成观感真值
├─ samples/
│  └─ README.md                   # 样本清单、来源、哈希、是否包含位置数据
└─ images/fromthephone/           # 用户原始样本，只读，不进入生成物目录
```

所有实验脚本、临时高光图、下载的编译工具与中间文件进入系统临时目录或明确的忽略目录，用完清理；不得留在 Git 工作区。若初始化 Git，先建立忽略规则再写入生成文件。大项目的关键算法和接口使用简体中文注释，文档随实现同步更新。

## 5. vivo 路线：从私有高光信息到可验证重建

### 阶段 V0：建立格式证据，不做美化

- 按字节记录 APP0–APP15、SOF/SOS/EOI、`streaminfo`、`streamdata` 和辅助 JPEG 偏移/长度。
- 读取主图/辅助图 ICC、EXIF、采样、尺寸、方向及 JSON 全部字段。
- 实现损坏段、截断、伪造长度、超大分配、非有限参数和零增益的拒绝路径。
- 保留四张样本和后续指定 XDR 开/关样本的哈希，不根据文件名判断 HDR。
- 结构识别采用“已验证的 Neo9 Pro 当前 OriginOS 结构”白名单；其它机型、系统版本或相机模式即使含相似字段也默认标记为未验证，不自动进入融合。
- 输出 `inspect` 报告，标明实测、推断与未知。

### 阶段 V1：验证几何与色彩，而不是直接套公式

- 主图 Display-P3 经 ICC 转为线性工作色域；辅助图按其 ICC 独立处理。
- 计算辅助图放大后的几何对应误差、边缘对齐、局部相关性和饱和像素关系。
- 建立可解释的对照：纯 SDR、仅增益、仅高光残差、仅显示端曲线。
- 任何候选模型都保存完整参数，不以肉眼“更好看”为唯一验收。

### 阶段 V2：候选重建模型

按顺序试验，每一步被证据否决即停止，不叠加不可解释处理：

1. **加性高光残差**：辅助图经传递函数解码、尺度标定和局部滤波后叠加到线性主图。
2. **增益/比值模型**：用辅助图估计局部 HDR/SDR 比值，限制增益和色度变化；`maxGain` 作为待验证约束，不直接当作已知曝光倍数。
3. **短曝光辅助图模型**：若数据表明辅助图保留高光原始纹理，则按主图高光区域进行曝光归一化与融合，暗部保持 SDR。
4. **显示端曲线分离**：若文件内重建无法接近相册，明确区分“文件重建不足”与“相册额外显示处理”，后者只能通过标定近似，不能声称来自原始数据。

允许加入暗部保护、色彩饱和度限制和高光去噪，但必须有对照组、参数记录和夜间场景验收，不能变成全图滤镜。

### 阶段 V3：显示适配与可选手机观感标定

首版以显示无关中间结果为准，不锁定手机或 HDR400 的绝对峰值：

- 中间结果记录线性工作色域、SDR 参考白、局部高光倍率/亮度关系和建议 HDR 容量；不用单一显示器的 400-nit 峰值作为数据上限。
- 输出 Ultra HDR 时，由标准增益图描述 HDR 相对 SDR 的余量，目标显示设备按自身能力应用；不为手机和 Windows 分别修改 SDR 基础图。
- 手机和 HDR400 的显示对照属于验证视图，不是写死在中间文件里的母版参数。

用户目前无法提供手机参考画面，首版不实施观感标定，也不把它作为已实现能力。若以后补充材料，推荐采集：

- 同一原始文件在相册 XDR 开/关的屏幕拍摄；固定手机亮度、环境光、屏幕色彩模式、拍摄设备曝光与白平衡。
- 同时保留系统截图作几何参考，但截图不能证明 HDR 屏幕亮度。
- 标定数据与原始文件分开存放，记录设备和设置；不假装截图就是物理 HDR 真值。

在没有上述参考时，验收只能写“合理 HDR 重建，手机 XDR 观感未验证”，不能写“已复现 XDR”。

## 6. NVIDIA 路线：AI 增强与统一 Ultra HDR 出口

### 路线选择

- **Luma**：保留为显示效果与参数对照工具。主程序没有图像导出 API，不通过屏幕截图作为 HDR 数据出口。
- **ComfyUI NVIDIA VFX Nodes**：作为可重复 AI 推理路径，固定提交 `38d790de…`、节点版本 0.2.1、`nvidia-vfx>=0.2`、CUDA 13.0+ 对应 PyTorch、官方 NVIDIA 驱动要求。

### 必须修正的输入/输出边界

1. 自带 `LoadImage` 对 Display-P3 不做 ICC 转换。先用本项目 `color.icc` 做色彩管理，再交给 NVIDIA。
2. NVIDIA Python API 要求 Rec.709/D65、gamma 2.2；不能直接把 sRGB 数值当作完全符合契约的输入。预处理节点显式处理传递函数。
3. TrueHDR 输出为 BT.2020/PQ RGB10A2。优先保留 PQ，避免节点 HLG 与核心固定 1000-nit 参考不一致。
4. 输出接 `ImageColorSpace` 转成明确的线性 HDR 中间结果，供共享编码器使用。
5. ComfyUI 核心没有 Ultra HDR JPEG 保存节点；新增极薄的“HDR + SDR → libultrahdr”节点，或调用本项目命令行编码器。不能用普通 `SaveImage` 冒充 Ultra HDR。

### 参数策略

- 第一组：对比/饱和 100、中灰 50、去色带开、峰值 400 nit，匹配 HDR400。
- 第二组：其他不变、峰值 650 nit，观察灯光扩展和色带。
- 仅当参考证据支持时才调整对比、饱和、中灰，不以全图更亮为优化目标。
- 每条结果记录 NVIDIA 驱动、ComfyUI、节点、模型轮子、参数和输入哈希。

## 7. 标准 Ultra HDR 输出与兼容性

### SDR 基础图

- 使用 ICC 正确转换的原始主图，保持普通 SDR 观感。
- 避免无意义的双重 JPEG 压缩；在 libultrahdr 允许的接口下使用原始压缩基础图或明确记录重编码质量与采样。
- 保留 EXIF/ICC 中必要部分，私有 vivo 段不盲目复制进标准输出。

### HDR 重建图与增益图

- vivo 路线：HDR 重建图来自私有辅助信息的可解释融合。
- NVIDIA 路线：HDR 重建图来自 TrueHDR，SDR 基础图仍来自原始主图。
- 将两者送入同一个 libultrahdr API-1 编码器，生成标准增益图和 MPF/XMP（以及所选版本支持的 ISO 元数据）。
- 标定 HDR 容量与显示余量，不将 `maxGain` 直接填入标准 `GainMapMax`。

### 辅助格式

同时可导出 10-bit AVIF PQ 用于检查 HDR 重建图；它是独立验证产物，不能替代标准 Ultra HDR 验收。暂不优先 HEIC/JPEG XL，以减少编码器和系统支持差异。

## 8. 验证与验收

### A. 输入与解析

- 四张原始样本的 SHA-256 在处理前后完全一致。
- 所有段偏移、长度、尺寸、ICC 和私有参数可复核。
- 损坏、截断、非标准输入不会崩溃、覆盖原图或产生伪标准输出。

### B. vivo 重建质量

- 暗部和普通区域与 SDR 基础图保持一致，无全图抬亮。
- 路灯/窗户等高光空间位置对齐，无明显光晕、重复纹理或彩色伪影。
- 夜景树叶、天空、暗建筑不过度提亮；霓虹与路灯颜色不过曝、不失饱和。
- 有手机参考时，在同环境拍屏做盲比；首版无参考时明确标为“合理 HDR 重建，手机 XDR 观感未验证”。
- 显示无关中间结果通过不同显示余量的解码检查，验证高光关系不会固定压缩到 HDR400 的约 400 nit 上限。

### C. NVIDIA 路线

- 节点真实执行，记录 `nvvfx.TrueHDR` 成功和 GPU/显存占用。
- Display-P3 与 Rec.709 gamma 2.2 的输入预处理经过单元测试。
- 输出是 BT.2020/PQ，不把 32-bit 浮点张量本身当成 HDR 文件。

### D. Ultra HDR 标准与解码

- libultrahdr 识别主图、增益图及元数据；不只检查 `hdrgm:Version` 字符串。
- 在 SDR 查看器看到正常基础图，不出现灰雾、暗淡 PQ 主图。
- 在支持 Ultra HDR 的 HDR 查看器看到高光扩展；Luma 应将其识别为原生 HDR，而不是再次 AI 增强。
- 在不同显示余量下检查平滑降级，不要求不同设备亮度完全一致。
- 交叉验证 Android/Chrome 或其他支持标准 Ultra HDR 的查看器；Windows Photos 只作为实测对象，不预设支持。

### E. 项目卫生

- 无临时下载、实验脚本、提取的私人高光图、编译缓存或输出文件污染 Git。
- 文档列明版本号对应的变更，不使用未解释的内部版本代号。
- 不将未运行的命令、未测试的查看器支持或拟合模型写成已验证事实。

## 9. 阶段交付顺序

1. **格式检查器与共享色彩/中间表示**：先能可靠解释输入。
2. **vivo 几何、色彩与候选融合实验**：先决定高光图到底是什么，再决定输出。
3. **共享 libultrahdr 编码与结构验证**：用已知 HDR/SDR 测试图先证明编码正确。
4. **NVIDIA ComfyUI 工作流**：接入相同编码出口，便于与 vivo 路线对比。
5. **手机观感标定和跨设备验证**：决定能否使用“复现 XDR”表述。
6. **批量处理和可选图形界面**：仅在核心质量验收后考虑。

## 10. 风险与停止条件

- 若私有高光图并非线性/增益数据，且无法从公开资料或受控样本确定语义，则保留实验模型，不输出“官方兼容 XDR”的承诺。
- 若无法获得手机参考，只能证明技术合理性和 Ultra HDR 标准兼容，不能证明观感复现。
- 若 NVIDIA 路线颜色偏差大于可接受范围，先修输入色彩，不用提高饱和度掩盖。
- 若标准 Ultra HDR 的低位深增益图导致高光色带，应记录格式限制并调整增益图分辨率/压缩，不重新提亮 SDR 基础图。
- 若 libultrahdr 不能保持原始 SDR 基础图，接受明确的重编码步骤并评估质量，不私造 MPF 容器。

## 11. 构建者可决定的事项

- 具体的 Python 色彩管理库、图像库和最小本地桥接方式，以官方文档、可维护性和 Windows 可构建性为准。
- libultrahdr 的固定提交、编译选项和桥接是命令行还是本地扩展；先验证官方接口再决定。
- 具体数值容差、候选模型的参数化形式，由 V0–V2 证据决定。
- 是否将编码器封装成 ComfyUI 自定义节点，优先复用共享核心，避免两套色彩实现。

## 12. 待批准

本文件是项目设计基线。用户批准后，下一步编写详细实施计划，再按阶段实现；本文件本身不代表任何转换器、节点或导出功能已经存在。
