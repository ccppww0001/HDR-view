# HDR Mapping and Windows Native Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留 HDR 内容层次，为 HDR400 生成专用映射，以直接 NVIDIA 模型和 Windows 原生 JPEG XR 扩展双管线。

**Architecture:** 共享线性 BT.2020/203-nit HDR 中间结果。vivo 与 NVIDIA 各自生成 HDR，400 映射只在指定目标上调用；官方 libultrahdr 和 Windows WIC 分别输出标准 Ultra HDR 与 JPEG XR。吸收 ComfyUI 参数契约与节点执行思想，不保留 ComfyUI 适配树。

**Tech Stack:** Python 3.12、NumPy/OpenCV/Pillow、C++17、CMake、Windows WIC、libultrahdr v2.0.2；可选 PyTorch 2.11.0+cu128 与 nvidia-vfx 0.2.0.0。

**Spec:** `docs/superpowers/specs/2026-11-17-hdr-mapping-windows-pipeline-design.md`

## Global Constraints

- 不修改原始照片、不覆盖已有输出；产品代码均在 `src/hdrview/`，默认输出 `output/<任务>/run-NNN`。
- 不操作桌面、不启动应用、不截图或 GUI 自动化；仅文件和命令行。
- 临时代码用完清理；持久终端必须可见，不创建无必要后台终端；不操作数据库。
- 大更改包含简体中文注释，文档与实现同步更新；不向用户展示没有解释的版本编号。
- vivo 始终标为“合理 HDR 重建，手机 XDR 观感未验证”；真实 NVIDIA 推理与合成契约测试严格分开。
- 不声称 Windows Photos HDR 显示已实测；参考开源实现时标明来源、版本和许可。
- 安装任何 NVIDIA/PyTorch 新依赖前列出环境路径、版本、来源与预计下载，等待用户确认。

## Review Focus

- 黑图、无高光图和全 SDR 输入：不得产生虚假 HDR 提亮。由 Task 1 的单元测试覆盖。
- 超高峰值、非有限值和极小 RGB 负分量：不得静默裁剪原 HDR；由 Task 1 的验证覆盖。
- Windows WIC 浮点支持差异：不可把失败或转换到 8 位当成功。由 Task 2 的真实系统编解码测试覆盖。
- 400 与 1000 的语义：1000 不得被误做 400 内容压缩；由 Task 4 的报告和端到端测试覆盖。
- 缺少 GPU 或 NVIDIA 二进制时：必须明确失败/跳过，不得假装运行。由 Task 3 的测试和显式环境检查覆盖。

---

### Task 1: 连续 vivo 融合与共享 HDR400 映射

**Files:**
- Modify: `src/hdrview/vivo/reconstruct.py`
- Create: `src/hdrview/mapping.py`
- Modify: `tests/unit/test_reconstruct_models.py`
- Create: `tests/unit/test_mapping.py`

**Interfaces:**
- Produces: `DisplayMapping(peak_nits: int = 400, knee_ratio: float = 0.8)`；`map_highlights(hdr: HdrImage, params: DisplayMapping) -> HdrImage`。
- Keeps: `ReconstructionParams(model, scale, max_gain_cap, highlight_threshold)` 与 `reconstruct(primary, auxiliary, params)`。
- Mapping output copies and augments provenance with `display_mapping="hdr400-highlight-compression"`, `target_nits`, `knee_ratio`；纯黑/SDR 不改变像素。

- [ ] 写失败测试：阈值两侧 `threshold*(1±1e-4)` 的融合相对变化小于 2%，黑辅助图不变，结果不超过原通道 `max_gain_cap` 容差。
- [ ] 运行 `python -m pytest tests/unit/test_reconstruct_models.py -v`，确认因不连续而失败。
- [ ] 用阈值至两倍阈值的平滑步进权重替换硬切换；阈值为 0 时仅严格大于零启用。关键模型写明“未验证的候选，不是 vivo 官方曲线”。
- [ ] 写失败测试：`map_highlights` 对 SDR `[0,1]` 不变；一系列 HDR 亮度保持严格次序；400nit 映射最大亮度不超过 `400/203`；高通量输出仍有限，knee 两段连续；无 HDR 时不增加亮度。
- [ ] 运行 `python -m pytest tests/unit/test_mapping.py -v`，确认因模块不存在而失败。
- [ ] 实现 spec 中 `DisplayMapping(400,0.8)` 与归一化有理曲线，BT.2020 亮度比例缩放 RGB，不做空间模糊。输入校验使用 `hdrview.io.intermediate._validate`。
- [ ] 运行上述测试及完整 `python -m pytest -q`；提交 `feat: preserve highlight transitions and map HDR400 content`。

### Task 2: Windows WIC JPEG XR 浮点 HDR 输出

**Files:**
- Create: `src/hdrview/native/hdrview_jxr.cpp`
- Modify: `src/hdrview/native/CMakeLists.txt`
- Move: `src/hdrview/build/Build-Native.ps1` → `src/hdrview/native/Build-Native.ps1` 并修根目录定位
- Create: `src/hdrview/output/jxr.py`
- Create: `tests/integration/test_jxr_windows.py`
- Modify: `tests/integration/test_native_bridge.py`

**Interfaces:**
- Consumes: Task 1 的 `HdrImage` 和已有严格 `intermediate.py` 读写器。
- Produces: `encode_jxr(hdr: HdrImage, output: Path) -> dict`；原生 `hdrview-jxr.exe encode --hdr <f16rgba> --meta <json> --output <new.jxr>`；`decode --input <jxr> --raw <new.f16rgba> --meta <new.json>`。
- 输出为 scRGB Rec.709 linear 浮点，参考白 80 nit；Python 回读转换为共享 BT.2020/203 nit 模型。
- 原生编码输入 203 nit 单位乘 `203/80`；通过 WIC `GUID_ContainerFormatWmp`、`GUID_WICPixelFormat64bppRGBAHalf` 编码并同库解码验证。不得转换到 8 位 JPEG 或声称 Photos 已实测。

- [ ] 写失败测试：实际构建后 JPEG XR 由 WIC 解码为浮点，4096×3072 样本可先以 16×16 替代；2.0 倍 203-nit 高光仍大于 SDR；尺寸、均值、色彩与有限值有效；重复输出拒绝覆盖。
- [ ] 运行 `python -m pytest tests/integration/test_jxr_windows.py -v`，确认因模块和可执行文件缺失而失败。
- [ ] 用 WIC COM RAII 实现严格 sidecar、尺寸、有限值、非负像素检查；通过临时输出与关闭后原子移动写 `.jxr`，禁止覆盖。不要自写 JPEG XR 容器。
- [ ] 新增构建目标并把脚本移入 `native/`，所有引用更新；保留现有 libultrahdr 目标和 ISO/XMP 双写。
- [ ] 执行 `pwsh -File src/hdrview/native/Build-Native.ps1 -Test` 与 JPEG XR 测试；如 WIC 拒绝所选像素格式，报告真实错误并修正格式，不静默降级。
- [ ] 运行完整测试；提交 `feat: add native Windows JPEG XR HDR output`。

### Task 3: 直接 NVIDIA 模型运行器取代 ComfyUI 适配树

**Files:**
- Modify: `src/hdrview/nvidia/comfy_workflow.py` → `src/hdrview/nvidia/runtime.py`（用 Git 重命名）
- Modify: `src/hdrview/nvidia/preprocess.py`
- Modify: `src/hdrview/nvidia/postprocess.py`
- Delete: `src/hdrview/comfyui/`、`src/hdrview/nvidia/input.py`、`tests/integration/test_comfy_truehdr.py`
- Modify: `tests/unit/test_nvidia_preprocess.py`、`tests/unit/test_nvidia_postprocess.py`
- Create: `tests/unit/test_nvidia_runtime.py`

**Interfaces:**
- Produces: `TrueHdrParams(contrast=100,saturation=100,middle_gray=50,luminance=1000,debanding=True)`；`unpack_pq_rgb10a2(packed) -> np.ndarray`；`truehdr_to_hdr(pq, *, source_sha256, params) -> HdrImage`；`run_truehdr(sdr: SdrImage, params: TrueHdrParams, source_sha256: str) -> HdrImage`。
- 模型调用顺序：可选超分在 TrueHDR 前；首版真实命令仅 TrueHDR，不假称已有超分。没有 nvvfx/CUDA 时失败且明确安装独立环境，不导入 ComfyUI。
- RGB10A2 无符号位提取参考 Comfy-Org NVIDIA VFX Nodes Apache-2.0 固定提交 `38d790ded00650681fa3645362efe28c8560cf40`；只保留必要最小实现。

- [ ] 写失败测试：默认峰值 1000；PQ 张量转为线性 BT.2020/203-nit；位解包不依赖 Torch；替代模型/运行时记录输入 gamma 2.2、参数、load 与 run 顺序；无 GPU 时明确异常。
- [ ] 运行新增单元测试，确认旧 API 不符合直接模型契约。
- [ ] 实现直接运行器，延迟导入 `nvvfx`/`torch`，隔离 GPU 生命周期，在 run 前 load，校验 DLPack 输出和原图哈希；真实 `HdrImage.provenance` 记录 `nvidia-vfx` 版本、参数及实测内容最大亮度。不得将 `luminance` 写成像素硬上限。
- [ ] 删除 ComfyUI 目录、静态工作流与节点；所有引用和测试随之更新。绝不制造一个已通过的真实 GPU 测试。
- [ ] 运行完整测试；提交 `refactor: run NVIDIA TrueHDR without ComfyUI`。

### Task 4: 统一命令行、输出与文档

**Files:**
- Modify: `src/hdrview/cli.py`
- Modify: `src/hdrview/io/output.py`
- Modify: `.gitignore`、`.slim` 如需要仅记录本次工作区，不复制源码
- Modify: `README.md`、`docs/verification.md`、`docs/research/{source-audit,color-pipeline,vivo-reconstruction}.md`
- Move: `docs/workflows/nvidia-comfyui.md` → `docs/workflows/nvidia-truehdr.md`
- Modify: `tests/integration/test_vivo_ultrahdr.py`、`tests/integration/test_nvidia_ultrahdr.py`

**Interfaces:**
- Consumes: Task 1–3 所有接口。
- Produces: `convert-vivo` 和 `convert-nvidia` 400/1000 各自输出 Ultra HDR JPEG，400 同时输出 JPEG XR；新增 `enhance-nvidia` 在隔离环境中直接运行，后续输出交给共享导出函数。
- 每条记录 `display_mapping`、`target_nits`、`windows_photos_hdr_verified=false`；400 映射在 JPEG 和 JPEG XR 前调用一次。1000 不使用 400 压缩。失败不可留下伪报告。
- `hdrview.native.Build-Native.ps1` 是唯一构建入口。

- [ ] 写失败测试：真实 vivo 样本 400 报告包含新映射且 HDR 容量为 `400/203`，1000 标记 `none` 且 `1000/203`；400 旁有同尺寸 JPEG XR；原始哈希不变。
- [ ] 运行指定集成测试，确认旧输出与报告不符合。
- [ ] 把映射和双输出接在共享 HDR 结果之后；保留中间结果输入绑定的 `convert-nvidia`，新增直接执行命令，不自动安装任何依赖。
- [ ] 删除主仓库遗留的空 `comfyui/`、`scripts/` 和旧 `native/build` 生成目录之前先验证它们不含有跟踪文件或用户文件；只清理已核验的构建残留。不重命名输出历史目录。
- [ ] 更新 README、参数说明、Windows 原生 HDR 边界、依赖来源与验证记录，明确 JPEG XR 与 PQ AVIF 的区别。
- [ ] 执行完整测试和单张真实样本生成到新的 `output/vivo/run-NNN`；核验 XMP/ISO、固定 HDR400 参考解码与 JPEG XR WIC 解码。不声称主观显示已验证。
- [ ] 提交 `feat: integrate display-aware HDR export and Windows native output`。

## Execution Notes

- 每项由有边界的实现者执行并单独审查；共享文件只允许 Task 4 在依赖完成后整合。
- 真实 NVIDIA 安装须用户明确确认；可先完成 CPU/原生格式与参数契约，不能因 GPU 未安装而宣称该路线完成。
- 最终生成报告、测试结果及用户手动验证待办保持分开。
