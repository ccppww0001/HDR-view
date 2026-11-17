# vivo XDR 与 NVIDIA AI 到标准 Ultra HDR 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Windows 上构建可验证的双管线工具：利用 Neo9 Pro 私有 XDR 高光信息或 NVIDIA TrueHDR 生成 HDR 图像，并以普通 SDR 主图为基础导出标准 Ultra HDR JPEG。

**Architecture:** Python 3.12 命令行核心负责输入安全、ICC/传递函数、HDR 中间表示与验证；vivo 和 NVIDIA 是互不混用的增强提供者。共享的薄 C++ 桥接使用官方 libultrahdr API-3（HDR raw + 原始压缩 SDR）编码，ComfyUI 只负责可复现的 NVIDIA 推理，不在其内部重复实现 Ultra HDR。

**Tech Stack:** Python 3.12、NumPy、Pillow ImageCms/LittleCMS、OpenCV、pytest、C++17/CMake、官方 libultrahdr、ComfyUI ≥0.35.0、ComfyUI NVIDIA VFX Nodes 0.2.1、CUDA 13.0+ 对应 PyTorch。

**Spec:** `docs/superpowers/specs/2026-11-16-vivo-xdr-ultra-hdr-design.md`

## Global Constraints

- 首版只支持当前 Neo9 Pro / 当前 OriginOS 已验证结构；其他输入必须显示“未验证/不支持”，不能套用猜测公式。
- 原始 JPEG 只读；处理前后 SHA-256 一致；默认输出到显式的新目录，任何覆盖都必须单独显式授权。
- vivo 首版验收为“合理 HDR 重建，手机 XDR 观感未验证”；无受控拍屏对照不得宣称复现 XDR。
- 中间 HDR 采用显示无关的线性光与色彩元数据，不锁死 HDR400 的 400-nit 上限。
- 标准 Ultra HDR 只能由官方 libultrahdr 编码；不把 vivo 辅助 JPEG 直接当增益图，不手写私有 MPF 冒充标准。
- SDR 基础图保持普通观感；不使用 PQ 编码图作为基础 JPEG，不用全图提亮伪装 XDR。
- NVIDIA 输入先执行 Display-P3 ICC 转换和 sRGB→Rec.709 gamma 2.2；PQ 输出保持 BT.2020/PQ 语义。
- Luma 只作显示对照；不以截图作为 HDR 文件导出路径。
- 依赖安装、SDK 下载与构建动作在执行前向用户说明；核心 Python 与 NVIDIA 环境隔离。
- 所有临时代码、下载、提取的高光图和编译缓存位于 `%LOCALAPPDATA%\Temp\opencode` 或 Git 忽略目录，用后清理。
- 重要算法/接口用简体中文注释，文档与实现同步更新；不引入无解释的版本编号。

## Review Focus

1. 恶意或损坏的 JPEG 段长度、尾部偏移和非有限增益不得造成越界、巨量分配或覆盖原图；Task 2、3 的截断/伪造长度/超大尺寸测试。
2. Display-P3 主图和辅助图若被误当 sRGB，会改变高光颜色；Task 4 的 ICC 像素/往返测试和 Task 8 的融合前色彩断言。
3. `maxGain` 不是已确认的标准 GainMapMax；Task 7 只把它作为候选约束，Task 9 必须证明增益来自 HDR/SDR 重建比值。
4. 普通查看器必须显示正常 SDR 基础图；Task 6 的 API-3 原始 SDR 字节与解码兼容性检查。
5. 没有手机参考不得把“接近 XDR”当已通过；Task 10 的报告必须显式写“手机 XDR 观感未验证”。
6. 8-bit HDRImage 在低光区域接近零，不能产生除以零或暗部放大；Task 8 的零高光、纯黑、极小值测试。
7. NVIDIA `IMAGE` 张量与 Ultra HDR 文件不能混淆；Task 12、13 必须验证 PQ 中间数据、MPF/增益图和最终文件，而非仅看张量。

## Shared Interfaces

以下接口是跨任务的契约，不允许在不同管线中改名复制：

```python
@dataclass(frozen=True)
class ColorState:
    primaries: Literal["display-p3", "rec709", "bt2020"]
    transfer: Literal["srgb", "rec709-gamma-2.2", "linear", "pq"]
    sdr_white_nits: float = 203.0

@dataclass(frozen=True)
class ImageDocument:
    source_path: Path
    sha256: str
    jpeg_segments: tuple[JpegSegment, ...]
    primary_icc: bytes | None
    exif: dict[str, str]
    vivo: VivoTrailer | None

@dataclass(frozen=True)
class HdrImage:
    rgba: Float32Array       # H×W×4，线性、scene-referred、非负；alpha=1
    color: ColorState        # primaries="bt2020", transfer="linear"
    hdr_capacity_max: float # 相对 SDR 的倍率，不是显示器 nit 峰值
    provenance: dict[str, str | float | int | bool]

@dataclass(frozen=True)
class SdrImage:
    rgba: UInt8Array         # H×W×4，sRGB 编码
    icc: bytes | None
    compressed_jpeg: bytes | None
```

中间文件采用 `RGBA float16` 原始像素 + JSON sidecar，记录尺寸、BT.2020/linear、通道顺序、stride、`sdr_white_nits=203.0`、`hdr_capacity_max`、来源参数和输入 SHA-256。float16 仅用于落盘，计算使用 float32。合法 HDR 通道必须有限、非负且不超过 float16 最大值 `65504`；`hdr_capacity_max` 必须有限且 `>=1`。编码前拒绝溢出，不能静默改成别的格式或用 `65504` 截断错误模型。禁止无 sidecar 的裸 `.bin` 被当成已知 HDR。

---

### Task 1: 项目骨架、隔离环境与只读输出契约

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `src/hdrview/__init__.py`, `src/hdrview/errors.py`, `src/hdrview/io/source.py`, `src/hdrview/io/output.py`
- Test: `tests/unit/test_source_output.py`

**Interfaces:**
- Produces: `read_source(path: Path) -> SourceBytes`、`SourceBytes(path, data, sha256)`、`create_output_dir(root: Path) -> Path`、`assert_original_unchanged(source: SourceBytes) -> None`。

- [x] **Step 1: 写只读和防覆盖失败测试**

测试目录符号链接/普通文件、重复运行、输出路径等于输入、处理后源哈希变化；要求默认拒绝覆盖，输出目录不能为原图所在目录。

- [x] **Step 2: 运行测试确认因模块不存在失败**

Run: `python -m pytest tests/unit/test_source_output.py -v`

- [x] **Step 3: 建立最小项目与安全的文件接口**

`pyproject.toml` 要求 Python `>=3.12,<3.13`，核心依赖先仅 `numpy`、`Pillow`、`opencv-python-headless`；测试依赖 `pytest`。源文件一次性读入，计算 SHA-256；所有后续步骤接收 `SourceBytes` 而不是重新打开原图。

- [x] **Step 4: 验证与提交**

Run: `python -m pytest tests/unit/test_source_output.py -v`

预期全部通过；README 说明尚无可用的 HDR 转换，不把骨架当完成品。用户若选择 Git，初始化后先提交 `.gitignore` 再添加生成物；提交信息 `chore: establish safe HDR project scaffold`。

---

### Task 2: JPEG 段扫描与 vivo 私有尾部定位

**Files:**
- Create: `src/hdrview/vivo/container.py`, `src/hdrview/model.py`, `src/hdrview/cli.py`
- Test: `tests/unit/test_vivo_container.py`, `tests/fixtures/make_jpeg_fixtures.py`

**Interfaces:**
- Consumes: `SourceBytes`。
- Produces: `scan_jpeg(data: bytes) -> tuple[JpegSegment, ...]`、`locate_vivo_trailer(data: bytes) -> VivoTrailer | None`、`JpegSegment(marker, offset, length)`、`VivoTrailer(info_offset, data_offset, info_length, data_length)`。

- [ ] **Step 1: 写二进制边界测试**

合成无 APP 段 JPEG、含 SOS 熵编码 `FF 00` 的主图、EOI 后 `streaminfo/streamdata`、截断段、段长小于 2、尾部偏移越界、非 JPEG、多个 EOI。不得通过全文件搜索 `FFD8` 判断辅助图位置。

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/unit/test_vivo_container.py -v`

- [ ] **Step 3: 实现有界扫描**

按 JPEG marker 长度读取 APP 段；SOS 后扫描到未填充的 EOI 并处理 `FF 00`/restart marker；仅允许一个经验证的 vivo trailer。记录偏移和长度，不直接解码任何私有像素。段扫描和尾部解析设定最大输入尺寸与数量上限。

- [ ] **Step 4: 对四张真实样本做只读核验**

Run: `python -m hdrview.cli inspect images/fromthephone --report <临时目录>/inspect.json`

预期主图 4096×3072，主 EOI 后为 `streaminfo`，`streamdata` 起点是合法 JPEG SOI；报告实测值而非预设 maxGain。

- [ ] **Step 5: 完整测试并提交**

Run: `python -m pytest tests/unit/test_vivo_container.py -v`

提交信息 `feat: parse bounded vivo JPEG trailers`。

---

### Task 3: vivo 辅助图、私有 JSON 与支持范围白名单

**Files:**
- Create: `src/hdrview/vivo/metadata.py`, `src/hdrview/vivo/auxiliary.py`, `docs/research/vivo-xdr-format.md`
- Test: `tests/unit/test_vivo_metadata.py`, `tests/integration/test_vivo_samples.py`

**Interfaces:**
- Consumes: `VivoTrailer`、`SourceBytes`。
- Produces: `parse_vivo_metadata(data: bytes) -> VivoMetadata`、`extract_auxiliary_jpeg(data: bytes) -> bytes`、`classify_support(document: ImageDocument) -> SupportStatus`；`VivoMetadata(max_gain: float | None, json: dict)`，`SupportStatus(supported: bool, reason: str)`。

- [ ] **Step 1: 写元数据与兼容性失败测试**

缺 JSON、截断 UTF-8、非数值、NaN/Infinity、负值/零值/超大 `maxGain`、非 Neo9 Pro、辅助图非 JPEG、主辅尺寸不匹配、错误 ICC、重复 trailer。要求“不支持”与“文件损坏”可区分。

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/unit/test_vivo_metadata.py -v`

- [ ] **Step 3: 实现严格解析和提取**

JSON 拒绝非有限值；辅助图必须由 Task 2 的精确偏移得到，不复用全文件字节搜索。首版只接受实测结构：`Make=vivo`、`Model=iQOO Neo9 Pro`、主辅尺寸 4096×3072 与 2048×1536、存在合法 Display-P3 ICC 和已知 trailer。`maxGain` 只记录，不推导曝光。

- [ ] **Step 4: 真实样本回归与文档**

断言四张样本的实测文件大小、辅助图尺寸和 `maxGain`；记录一张相册无 HDR 的样本仍可能有辅助数据，不将显示状态当文件格式判据。更新 `docs/research/vivo-xdr-format.md`。

- [ ] **Step 5: 测试并提交**

Run: `python -m pytest tests/unit/test_vivo_metadata.py tests/integration/test_vivo_samples.py -v`

提交信息 `feat: validate vivo auxiliary images and metadata`。

---

### Task 4: ICC、传递函数与 HDR 中间表示

**Files:**
- Create: `src/hdrview/color/icc.py`, `src/hdrview/color/transfer.py`, `src/hdrview/color/gamut.py`, `src/hdrview/io/intermediate.py`, `src/hdrview/model.py`, `docs/research/color-pipeline.md`
- Test: `tests/unit/test_color.py`, `tests/unit/test_intermediate.py`

**Interfaces:**
- Produces: `decode_with_icc(jpeg: bytes) -> SdrImage`、`srgb_to_linear(rgb)`、`linear_to_srgb(rgb)`、`srgb_to_rec709_gamma22(rgb)`、`pq_to_linear_bt2020(rgb, peak_nits=10000.0)`、`write_intermediate(image: HdrImage, stem: Path) -> IntermediatePaths`、`read_intermediate(stem: Path) -> HdrImage`。

- [ ] **Step 1: 写色彩参考值测试**

sRGB 0/0.04045/0.5/1 分段点；gamma 2.2 差异；PQ 0、100、203、1000、10000 nit 对应值；P3 红色到 Rec.709 的色域处理；负值、NaN、Infinity 和 alpha。PQ 往返容差以 float32 计算，不要求整数 10-bit 无损。

- [ ] **Step 2: 写中间表示失败测试**

sidecar 缺失、错误尺寸/stride/通道、错误色彩空间、超过 `65504` 的 float16 溢出、非有限值、负 HDR、输入哈希缺失、`hdr_capacity_max<1` 或非 BT.2020 linear 一律拒绝。

- [ ] **Step 3: 运行确认失败**

Run: `python -m pytest tests/unit/test_color.py tests/unit/test_intermediate.py -v`

- [ ] **Step 4: 实现单一色彩入口**

Pillow ImageCms 读取嵌入 ICC 并转到 sRGB，不能 `convert("RGB")` 冒充 ICC；之后显式线性化并按 Rec.709→BT.2020 矩阵转换。所有超色域策略记录到 provenance，不能静默裁剪高光。中间 sidecar 记录线性光相对于 `203 nit` SDR 参考白，不锁定显示器峰值。

- [ ] **Step 5: 真实样本与测试**

Run: `python -m pytest tests/unit/test_color.py tests/unit/test_intermediate.py -v`

补充真实样本：Display-P3 ICC 被读取，输出 `SdrImage` 的 sRGB ICC 存在，主图不被覆盖。提交信息 `feat: add color-managed HDR interchange`。

---

### Task 5: 固定官方 libultrahdr 的 Windows 构建

**Files:**
- Create: `native/README.md`, `native/CMakeLists.txt`, `native/src/hdrview_ultrahdr.cpp`, `scripts/Build-Native.ps1`
- Test: `tests/integration/test_native_bridge.py`

**Interfaces:**
- Produces: `hdrview-ultrahdr.exe encode --hdr <raw> --meta <json> --sdr <original.jpg> --output <new.jpg>` 和 `inspect --input <file> --json <report>`。

- [ ] **Step 1: 写构建输入/失败测试**

缺失编译器、缺失官方源码、哈希不符、输出已存在、sidecar 缺失、非法尺寸时必须非零退出且不得生成部分目标。

- [ ] **Step 2: 固定官方来源并构建**

选用经过实际 `git ls-remote` 验证的官方 libultrahdr 稳定 tag/commit，将 URL、完整提交、源码压缩包 SHA-256、构建选项写入 `native/README.md`；禁止浮动的 `main`。使用 C++17、JPEG-only、`UHDR_ENABLE_HEIF=OFF`、示例/测试关闭（自身测试除外）、Windows Unicode 路径。依赖放在临时/忽略工具目录，不能后台执行安装程序。

- [ ] **Step 3: 实现薄桥接**

只负责文件、sidecar、维度/stride、RGBA float16 与原始 SDR 字节；不实现增益公式或私有容器。调用 API-3：HDR raw + compressed SDR。输出使用临时文件后原子改名，错误时删除临时文件。

- [ ] **Step 4: 构建并验证自身桥接**

Run: `pwsh -File scripts/Build-Native.ps1 -Test`

预期桥接单元/集成测试通过；保存编译器、libultrahdr、JPEG 和桥接源码版本。提交信息 `build: add pinned libultrahdr bridge`。

---

### Task 6: 已知 HDR 合成图到标准 Ultra HDR 的垂直切片

**Files:**
- Create: `src/hdrview/output/ultrahdr.py`, `src/hdrview/verify/structure.py`, `src/hdrview/verify/roundtrip.py`, `docs/verification.md`
- Test: `tests/integration/test_ultrahdr_roundtrip.py`

**Interfaces:**
- Consumes: `HdrImage`、`SdrImage`、Task 5 桥接。
- Produces: `encode_ultrahdr(hdr: HdrImage, sdr: SdrImage, output: Path) -> EncodeReport`、`inspect_ultrahdr(path: Path) -> UltraHdrReport`、`decode_reference(path: Path, display_boost: float) -> HdrImage`。

- [ ] **Step 1: 写已知答案的合成 HDR 测试**

构造 64×64 SDR 灰阶与仅中央高光为 SDR 4 倍的 BT.2020 linear HDR；以原始压缩 SDR JPEG 作为基础。预期 `is_uhdr_image=1`、主图尺寸一致、增益图尺寸合法、SDR 解码接近原主图、HDR 中央显著大于周边、暗部不被全图抬亮。

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/integration/test_ultrahdr_roundtrip.py -v`

- [ ] **Step 3: 实现编码与独立检查**

编码器从 HDR/SDR 实际比值计算增益，不接受调用者手工填写 `GainMapMax`。验证除了 `is_uhdr_image`，还读取 MPF、XMP/ISO、基础 JPEG、增益图 JPEG 与元数据；不依赖单一标签。记录源 JPEG 是否在输出容器中保持原始字节；若官方重打包改变字节，以图像/元数据对比验收而非假定字节一致。

- [ ] **Step 4: 验证 SDR/HDR 两种解码**

用官方解码器以 `display_boost=1.0` 和多个大于 1 的值解码，验证 SDR 观感与 HDR 高光关系；Luma 在后续手动验收中应显示原生 HDR、禁用 TrueHDR。

- [ ] **Step 5: 完整验证并提交**

Run: `python -m pytest tests/integration/test_ultrahdr_roundtrip.py -v`

提交信息 `feat: encode verified Ultra HDR from linear HDR`。

---

### Task 7: vivo 几何/色彩诊断与候选模型选择

**Files:**
- Create: `src/hdrview/vivo/diagnostics.py`, `src/hdrview/vivo/reconstruct.py`, `docs/research/vivo-reconstruction.md`
- Test: `tests/integration/test_vivo_diagnostics.py`, `tests/unit/test_reconstruct_models.py`

**Interfaces:**
- Consumes: `ImageDocument`、辅助 JPEG、`decode_with_icc`。
- Produces: `analyze_vivo_alignment(document) -> AlignmentReport`、`ReconstructionParams(model, scale, max_gain_cap, highlight_threshold)`、`reconstruct(document, params) -> HdrImage`。

- [ ] **Step 1: 写已知几何/模型测试**

合成平移/缩放辅助图、零高光、饱和灯点、P3 彩色高光、主图暗部和不同 `maxGain`；输出诊断必须包括缩放后边缘对应、主辅亮度相关性、主图饱和区与辅助亮区重叠率。不得用全图相关性一个数字决定公式。

- [ ] **Step 2: 对真实样本产出诊断，不生成最终照片**

Run: `python -m hdrview.cli analyze-vivo <原始样本> --report <临时目录>/alignment.json`

检查辅助图是否严格空间对齐、是否只含高光残差、P3 主辅色域关系和不同 maxGain 的分布。将证据和仍未知的传递函数写入研究文档。

- [ ] **Step 3: 写候选模型的失败测试**

同一输入依次测试 additive-residual、ratio、short-exposure 三种明确模型；暗区输入为零时输出不放大、无 NaN；辅助为零时回到原始 SDR 对应的线性值；高倍率不得无限扩散到全图。

- [ ] **Step 4: 实现可插拔模型和证据选择**

仅实现诊断支持的候选，不允许三个模型任意串联。每个结果记录 `model`、参数、cap、残差统计和未验证声明；`maxGain` 只作候选 cap/比较变量，不能直接当标准增益元数据。若无法区分模型，保留多个实验输出并标记 `research_only=true`。

- [ ] **Step 5: 测试与人工研究关卡**

Run: `python -m pytest tests/unit/test_reconstruct_models.py tests/integration/test_vivo_diagnostics.py -v`

验收不是“模型更亮”，而是选定模型的假设得到样本证据支持；否则暂停正式 vivo 导出，仅允许实验输出。提交信息 `feat: add evidence-based vivo reconstruction diagnostics`。

---

### Task 8: vivo HDR 重建与可解释质量报告

**Files:**
- Create: `src/hdrview/vivo/fuse.py`, `src/hdrview/verify/compare.py`, `docs/workflows/vivo-reconstruction.md`
- Test: `tests/integration/test_vivo_reconstruction.py`

**Interfaces:**
- Consumes: Task 7 的选定 `reconstruct` 与 `ReconstructionParams`。
- Produces: `reconstruct_vivo(document, params) -> ReconstructionResult`，包含 `HdrImage`、对齐/高光/暗部/色彩统计和 `xdr_appearance_verified=False`。

- [ ] **Step 1: 写夜景失败测试**

测试黑色天空、低亮树叶、饱和路灯、白色窗灯、彩色霓虹；普通区域不得整体抬亮，高光不得越界/NaN，高饱和色不得无说明裁剪。辅助图纯黑时输出与 SDR 线性值在容差内一致。

- [ ] **Step 2: 实现融合和局部约束**

融合在线性 BT.2020 工作空间进行；空间滤波不得跨越高对比边缘造成明显光晕。可选暗部保护/去噪必须独立开关并记录，默认不叠加全图对比、饱和或曝光滤镜。

- [ ] **Step 3: 四张样本端到端生成 HDR 中间结果**

Run: `python -m hdrview.cli reconstruct-vivo images/fromthephone --output <临时目录>/vivo-intermediate`

验证四张中间图尺寸、色彩 sidecar、有限值、来源哈希、`xdr_appearance_verified=false`。只对有证据的模型继续；否则保留研究状态。

- [ ] **Step 4: 人工高光对照与报告**

生成 SDR、辅助图和重建预览（预览仅作几何/色彩诊断，不证明 HDR 屏幕亮度）；检查窗户/灯点空间位置、光晕、彩色伪影、暗部保护。更新质量报告和未验证项。

- [ ] **Step 5: 测试并提交**

Run: `python -m pytest tests/integration/test_vivo_reconstruction.py -v`

提交信息 `feat: reconstruct bounded HDR from vivo highlights`。

---

### Task 9: vivo 到标准 Ultra HDR 及显示余量验收

**Files:**
- Modify: `src/hdrview/cli.py`, `docs/verification.md`
- Test: `tests/integration/test_vivo_ultrahdr.py`

**Interfaces:**
- Consumes: `reconstruct_vivo`、`decode_with_icc`、`encode_ultrahdr`。
- Produces: `hdrview convert-vivo <input> --output <dir>` 和包含 `xdr_appearance_verified=false` 的完整报告。

- [ ] **Step 1: 写双路线隔离测试**

vivo 输出不得调用 NVIDIA；输入 SDR 基础图来自原主图，不来自重建图重新色调映射；无私有 trailer 的普通 JPEG 必须走 SDR/未支持路径而不是伪造增益。

- [ ] **Step 2: 实现 vivo 转换命令**

仅接受 Task 3 白名单，按 Task 7 证据选定模型；编码使用 Task 6 共享 API-3。不得把 `maxGain` 直接写入 `GainMapMax`，必须来自 HDR 与 SDR 的实际比值。

- [ ] **Step 3: 验证输出标准结构与不同显示余量**

Run: `python -m hdrview.cli verify <输出目录> --json <临时目录>/verification.json`

验证官方 `is_uhdr_image`、基础图、增益图、显示 boost=1 和 >1 的解码、颜色与几何；生成“合理 HDR 重建，手机 XDR 观感未验证”报告。

- [ ] **Step 4: Luma/跨查看器手动验收**

Luma 应识别原生 HDR、RTX 开关禁用；普通查看器应显示正常 SDR。记录实际查看器版本、Windows HDR 状态和屏幕拍屏，不把截图亮度当证据。

- [ ] **Step 5: 测试并提交**

Run: `python -m pytest tests/integration/test_vivo_ultrahdr.py -v`

提交信息 `feat: export vivo reconstruction as standard Ultra HDR`。

---

### Task 10: 发布 vivo 研究版文档与明确边界

**Files:**
- Create: `docs/verification.md`, `samples/README.md`, `docs/research/vivo-reconstruction.md`
- Modify: `README.md`

- [ ] **Step 1: 写文档一致性检查**

检查所有“复现 XDR”均有“未验证”限定；输出格式明确为标准 Ultra HDR JPEG；只承诺 Neo9 Pro 当前结构；中间结果无 400-nit 硬上限。

- [ ] **Step 2: 整理样本与复现记录**

记录四张样本 SHA-256、来源、隐私提示、当前参数与失败样例；原图不复制进 fixtures。文档列出此版本实际支持的输入、模型、输出和验证，不写虚构版本代号。

- [ ] **Step 3: 运行 vivo 全部验证**

Run: `python -m pytest tests/unit tests/integration -k "vivo or ultrahdr or color or source" -v`

预期通过；任何被暂停的模型必须标为研究输出，不能进入正式转换命令。

- [ ] **Step 4: 提交独立可验收的 vivo 里程碑**

提交信息 `docs: define verified vivo research release evidence`。此节点可以交付真实 Ultra HDR 编码与有边界的 vivo 研究工具，再独立推进 NVIDIA。

---

### Task 11: NVIDIA 预处理与 ComfyUI 固定工作流

**Files:**
- Create: `src/hdrview/nvidia/preprocess.py`, `src/hdrview/nvidia/comfy_workflow.py`, `comfyui/workflows/nvidia_to_hdr.json`, `comfyui/custom_nodes/hdrview_nodes/__init__.py`, `comfyui/custom_nodes/hdrview_nodes/color_io.py`, `comfyui/README.md`
- Test: `tests/unit/test_nvidia_preprocess.py`, `tests/unit/test_comfy_workflow.py`

**Interfaces:**
- Consumes: `decode_with_icc`、`srgb_to_rec709_gamma22`。
- Produces: `prepare_truehdr_input(sdr: SdrImage) -> Float32Array`、ComfyUI `HdrViewPrepareTrueHDR`（返回 `(B,H,W,3)` Rec.709 gamma 2.2 IMAGE）、`build_workflow(input_png: Path, params: TrueHdrParams) -> dict`、`TrueHdrParams(contrast=100, saturation=100, middle_gray=50, luminance=400, debanding=True, output_colorspace="HDR PQ")`。

- [ ] **Step 1: 写输入契约与工作流失败测试**

P3 输入必须经过 ICC；prepare 输出 Rec.709/D65 gamma 2.2；工作流必须含 `LoadImage → HdrViewPrepareTrueHDR → RTXTrueHDR → HdrViewSaveLinear` 的真实链接、`output_colorspace=HDR PQ`、debanding=true，不得包含默认 HLG、普通 Save Image 或假 Ultra HDR 节点。

- [ ] **Step 2: 实现 ICC 预处理和工作流生成**

先生成标准 sRGB PNG 作为 ComfyUI 输入，再由实际连接的 `HdrViewPrepareTrueHDR` 节点转成 gamma 2.2；不能只在外部脚本生成 gamma 2.2 文件后又让 LoadImage 改解释。节点复用 Task 4 的共享转换，固定 ComfyUI ≥0.35.0、VFX Nodes 提交 `38d790de…`、Python 3.12、PyTorch cu130+、NVIDIA 驱动≥570.65。`HdrViewSaveLinear` 在本任务只定义接口，Task 12 完成实现。

- [ ] **Step 3: 测试和文档**

Run: `python -m pytest tests/unit/test_nvidia_preprocess.py tests/unit/test_comfy_workflow.py -v`

文档明确 `nvidia-vfx` 官方索引、模型随 wheel、独立环境、依赖安装前确认；不写未实测的速度/显存数值。

- [ ] **Step 4: 提交**

提交信息 `feat: prepare color-correct NVIDIA HDR workflow`。

---

### Task 12: NVIDIA PQ 输出回收与统一 HDR 中间表示

**Files:**
- Create: `src/hdrview/nvidia/postprocess.py`
- Modify: `comfyui/custom_nodes/hdrview_nodes/__init__.py`, `comfyui/custom_nodes/hdrview_nodes/color_io.py`
- Test: `tests/unit/test_nvidia_postprocess.py`, `tests/integration/test_comfy_truehdr.py`

**Interfaces:**
- Consumes: 官方 `RTXTrueHDR` 输出 `(B,H,W,3) float32` BT.2020/PQ。
- Produces: ComfyUI `HdrViewSaveLinear` 节点（写出 Task 4 中间 raw+sidecar）、`read_truehdr_output(stem: Path) -> HdrImage`。

- [ ] **Step 1: 写 PQ 数值与生命周期测试**

验证 10-bit 解包位序、PQ 100/203/1000 nit 对应线性值、批量维度、alpha、DLPack 克隆发生时机、sidecar 与输入哈希；无 CUDA 时跳过 GPU 集成测试而不是伪造通过。

- [ ] **Step 2: 实现最薄的自定义节点**

仅做必要的 gamma/ICC 输入、PQ→linear 转换与中间保存；直接复用共享 Python 核心，不复制矩阵常量。官方 `RTXTrueHDR` 保持不动，保存节点不直接写 Ultra HDR。

- [ ] **Step 3: 实际 GPU 执行**

Run: 在用户可见的 ComfyUI 终端加载固定工作流，输入一张主图，参数 400 nit 与 650 nit 各一份。

记录节点版本、真实 NVIDIA 执行、GPU/显存、耗时与输出 sidecar；失败时记录 `nvvfx` 错误，不以 SDR 图像代替 HDR。

- [ ] **Step 4: 验证并提交**

Run: `python -m pytest tests/unit/test_nvidia_postprocess.py tests/integration/test_comfy_truehdr.py -v`

提交信息 `feat: preserve NVIDIA PQ output as linear HDR`。

---

### Task 13: NVIDIA 到 Ultra HDR 与 AVIF 诊断输出

**Files:**
- Create: `src/hdrview/output/avif.py`, `src/hdrview/cli.py`, `docs/workflows/nvidia-comfyui.md`
- Test: `tests/integration/test_nvidia_ultrahdr.py`

**Interfaces:**
- Consumes: `read_truehdr_output`、原始 `SdrImage`、`encode_ultrahdr`。
- Produces: `hdrview convert-nvidia <original> --intermediate <stem> --output <dir>`、`save_avif_pq(hdr, path, peak_nits)`。

- [ ] **Step 1: 写输入一致性和编码失败测试**

中间结果哈希与原图不符、尺寸不符、色彩不符、PQ 峰值非法、普通 SDR 中间结果均拒绝。SDR 基础图必须来自原始 JPEG，不得使用 AI 输出压回 SDR。

- [ ] **Step 2: 实现 NVIDIA 转换与可选 AVIF**

官方 Ultra HDR 编码仍走 Task 6；AVIF 仅用于独立检查 BT.2020/PQ 中间结果，10-bit、色彩标记正确，不宣称完整 HDR10 母版。

- [ ] **Step 3: 双参数验证与 Luma 对照**

对 400/650 nit 两份 Ultra HDR 检查结构、显示余量、灯色、暗部和色带；Luma 原生 HDR 显示与 ComfyUI 原始 AI 显示对照，记录不同编码/显示适配造成的差异。

- [ ] **Step 4: 测试并提交**

Run: `python -m pytest tests/integration/test_nvidia_ultrahdr.py -v`

提交信息 `feat: export NVIDIA TrueHDR as Ultra HDR`。

---

### Task 14: 双管线整体验收、文档与清理

**Files:**
- Create: `docs/verification.md`, `docs/research/source-audit.md`
- Modify: `README.md`, `samples/README.md`

- [ ] **Step 1: 运行全部自动测试**

Run: `python -m pytest tests/unit tests/integration -v`

预期全部通过；GPU 不可用只允许明确 SKIP 对应集成测试，报告中不得写“NVIDIA 实测通过”。

- [ ] **Step 2: 核对两条管线独立性**

vivo 结果不得包含 NVIDIA provenance；NVIDIA 结果不得使用 vivo 辅助图；两者 SDR 基础图均来自原主图；Ultra HDR 共用同一编码入口和验证函数。

- [ ] **Step 3: 实际显示与兼容性记录**

Windows HDR Calibration 后，使用 Luma、Windows Photos、一个明确支持 Ultra HDR 的 HDR 查看器交叉验证；记录各版本、显示设备、观察结果与不支持项。Windows Photos 不预设成功。

- [ ] **Step 4: 清理与最终证明**

删除临时下载、实验脚本、辅助 JPEG、构建缓存与未采用生成物；复核四张原图 SHA-256 和 Git 状态。原始样本、安装包不被修改或删除。

- [ ] **Step 5: 最终提交**

提交信息 `docs: record dual-pipeline HDR verification and limitations`。交付内容明确：真实标准 Ultra HDR、vivo 合理重建但未验证 XDR 观感、NVIDIA AI 增强、跨设备能力边界。

---

## Dependency Order and Execution Lanes

1. Task 1–6 是共享基础，按顺序执行；Task 6 先证明标准编码，避免 vivo 公式和容器错误混杂。
2. Task 7–10 是 vivo 研究管线，依赖 Task 1–6；Task 7 的证据关卡未通过不得把模型变成正式功能。
3. Task 11–13 是 NVIDIA 管线，可在 Task 1–6 后与 vivo 并行；不得与 vivo 并行修改同一文件，CLI/文档由 Task 14 统一协调。
4. Task 14 依赖所有完成或明确暂停的分支，并处理版本、验证和清理。

## Execution Notes

- 每个任务遵循测试先行：失败测试 → 最小实现 → 定向测试 → 回归测试 → 审查 → 提交。
- 本目录当前不是 Git 仓库；用户选择执行方式后再决定是否初始化 Git 或建立隔离工作区，不能自行假设已有分支。
- 实际安装 ComfyUI、CUDA PyTorch、NVIDIA wheel、编译器或下载 libultrahdr 前，向用户展示版本、来源、目标和环境隔离方案。
- 需要长期运行的 ComfyUI/构建终端使用用户可见的原生终端，任务结束关闭；不启动无意义重复进程。
- 不把源码审查、合成图测试或 SDR 预览当作真实 HDR 观感验证。
