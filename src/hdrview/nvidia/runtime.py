"""直接调用官方 nvidia-vfx TrueHDR，并将 PQ 输出转为共享 HDR 中间表示。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
import importlib.metadata

import numpy as np

from hdrview.color.transfer import pq_to_linear_bt2020
from hdrview.model import ColorState, HdrImage, SdrImage
from hdrview.nvidia.preprocess import prepare_truehdr_input

_DEPENDENCY_INSTRUCTIONS = (
    "NVIDIA TrueHDR 需要安装 nvidia-vfx==0.2.0.0 和 PyTorch 2.11.0+cu128 "
    "到隔离的 .venv-nvidia；请手动安装，当前工具不会自动安装依赖"
)


@dataclass(frozen=True)
class TrueHdrParams:
    """官方 TrueHDR 的显式参数；luminance 是目标声明而非像素硬上限。"""

    contrast: int = 100
    saturation: int = 100
    middle_gray: int = 50
    luminance: int = 1000
    debanding: bool = True

    def validate(self) -> None:
        ranges = (
            ("contrast", self.contrast, 0, 200),
            ("saturation", self.saturation, 0, 200),
            ("middle_gray", self.middle_gray, 10, 100),
            ("luminance", self.luminance, 400, 2000),
        )
        for name, value, minimum, maximum in ranges:
            # bool 是 int 的子类，必须排除，避免无效参数悄悄传给原生模型。
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError(f"TrueHDR {name} 必须是 [{minimum},{maximum}] 范围内的整数")
        if not isinstance(self.debanding, bool):
            raise ValueError("TrueHDR debanding 必须是 bool")


def _validate_source_sha256(source_sha256: str) -> None:
    if not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in source_sha256):
        raise ValueError("TrueHDR 结果必须携带有效的原始图片 SHA-256")


def unpack_pq_rgb10a2(packed: np.ndarray) -> np.ndarray:
    """将 H×W uint32 RGB10A2 解包为 H×W×3 float32 PQ，忽略 alpha。"""

    values = np.asarray(packed)
    if values.ndim != 2 or values.shape[0] < 1 or values.shape[1] < 1:
        raise ValueError("RGB10A2 输入必须是非空 H×W 二维数组")
    if values.dtype != np.uint32:
        raise ValueError("RGB10A2 输入必须使用 uint32，避免有符号位移和溢出")
    # 最小位提取参考 Comfy-Org/ComfyUI_Nvidia_VFX_Nodes，固定提交
    # 38d790ded00650681fa3645362efe28c8560cf40，Apache-2.0；不复制其节点框架。
    red = (values & np.uint32(0x3FF)).astype(np.float32)
    green = ((values >> np.uint32(10)) & np.uint32(0x3FF)).astype(np.float32)
    blue = ((values >> np.uint32(20)) & np.uint32(0x3FF)).astype(np.float32)
    return (np.stack((red, green, blue), axis=-1) / np.float32(1023)).astype(np.float32)


def truehdr_to_hdr(pq: np.ndarray, *, source_sha256: str, params: TrueHdrParams) -> HdrImage:
    """转换 PQ 像素；此函数本身不执行、也不宣称执行了 NVIDIA GPU 推理。"""

    params.validate()
    _validate_source_sha256(source_sha256)
    encoded = np.asarray(pq)
    if encoded.ndim != 3 or encoded.shape[2] != 3 or encoded.shape[0] < 1 or encoded.shape[1] < 1:
        raise ValueError("TrueHDR PQ 输出必须是非空 H×W×3 RGB")
    if not np.issubdtype(encoded.dtype, np.number) or np.issubdtype(encoded.dtype, np.complexfloating):
        # 禁止 astype 静默丢弃虚部；PQ 只接受实数编码。
        raise ValueError("TrueHDR PQ 输出必须是实数数值数组")
    encoded = encoded.astype(np.float32, copy=False)
    if not np.all(np.isfinite(encoded)) or np.any((encoded < 0) | (encoded > 1)):
        raise ValueError("TrueHDR PQ 输出必须是有限的 [0,1] 数值")
    # 使用项目已有的精确 PQ 公式，以绝对 nit 解码后统一到 203 nit 参考白。
    linear = (pq_to_linear_bt2020(encoded) / np.float32(203)).astype(np.float32)
    rgba = np.concatenate((linear, np.ones((*linear.shape[:2], 1), dtype=np.float32)), axis=2)
    capacity = max(1.0, float(np.max(linear)))
    provenance = {
        "pipeline": "nvidia-truehdr",
        "source_sha256": source_sha256,
        **asdict(params),
    }
    return HdrImage(rgba, ColorState("bt2020", "linear"), capacity, provenance)


def _import_runtime() -> tuple[object, object]:
    # 延迟导入保证无 GPU 的纯转换与中间结果读取仍可工作。
    try:
        torch = importlib.import_module("torch")
        nvvfx = importlib.import_module("nvvfx")
    except ImportError as error:
        raise RuntimeError(_DEPENDENCY_INSTRUCTIONS) from error
    return torch, nvvfx


def _check_nvidia_cuda(torch: object) -> None:
    try:
        available = bool(torch.cuda.is_available())
        device_name = str(torch.cuda.get_device_name(0)) if available else ""
    except Exception as error:
        raise RuntimeError("无法检查 NVIDIA CUDA 设备；TrueHDR 不会在未验证的设备上运行") from error
    if not available:
        raise RuntimeError("没有可用 CUDA；请使用支持 CUDA 的 NVIDIA GPU 和隔离 .venv-nvidia 环境")
    if "nvidia" not in device_name.casefold():
        raise RuntimeError(f"CUDA 设备 0 不是 NVIDIA GPU：{device_name}")


def _version(nvvfx: object) -> str:
    """优先读取模块版本；非字符串或缺失时查询已安装发行包元数据。"""

    for name in ("__version__", "VERSION", "version"):
        value = getattr(nvvfx, name, None)
        if isinstance(value, str) and value:
            return value
    try:
        return importlib.metadata.version("nvidia-vfx")
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError("无法确定 nvidia-vfx 版本；TrueHDR 要求 nvidia-vfx==0.2.0.0") from error


def run_truehdr(sdr: SdrImage, params: TrueHdrParams, source_sha256: str) -> HdrImage:
    """在 CUDA 设备 0 上直接运行一次官方 TrueHDR，不依赖 ComfyUI。"""

    params.validate()
    _validate_source_sha256(source_sha256)
    rgb = prepare_truehdr_input(sdr)
    torch, nvvfx = _import_runtime()
    version = _version(nvvfx)
    if version != "0.2.0.0":
        raise RuntimeError(f"nvidia-vfx 版本必须为 0.2.0.0，实际为 {version}")
    _check_nvidia_cuda(torch)
    constructor = getattr(nvvfx, "TrueHDR", None)
    if constructor is None:
        raise RuntimeError(_DEPENDENCY_INSTRUCTIONS)
    try:
        # 官方 API 固定为 Rec.709 gamma 2.2 CHW float32，模型在 run 前 load。
        with constructor(
            contrast=params.contrast,
            saturation=params.saturation,
            middle_gray=params.middle_gray,
            luminance=params.luminance,
            debanding_off=int(not params.debanding),
            device=0,
        ) as model:
            model.load()
            with torch.cuda.device(0):
                tensor = torch.from_numpy(rgb).permute(2, 0, 1).contiguous().to(device="cuda:0", dtype=torch.float32)
                # 官方默认流使用句柄 0；不要创建或切换私有流，避免 nvidia-vfx 原生执行失败。
                result = model.run(tensor, stream_ptr=0)
                # 克隆 DLPack 视图以隔离模型输出生命周期，位解包仍在 GPU 完成。
                packed = torch.from_dlpack(result.image).clone()
                # 必须按源图 H×W 解释原生输出，禁止模型异常尺寸或有符号数据进入位解包。
                if tuple(packed.shape) != rgb.shape[:2]:
                    raise RuntimeError(f"NVIDIA TrueHDR 输出尺寸不匹配：期望 {rgb.shape[:2]}，实际 {tuple(packed.shape)}")
                if packed.dtype != torch.uint32:
                    raise RuntimeError(f"NVIDIA TrueHDR RGB10A2 输出必须使用 uint32，实际为 {packed.dtype}")
                # PyTorch 2.11 的 CUDA uint32 不支持按位运算；先复制到主机，再用 NumPy 解包。
                pq = unpack_pq_rgb10a2(packed.cpu().numpy())
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("NVIDIA TrueHDR 直接执行失败；未生成伪造的 HDR 结果") from error
    hdr = truehdr_to_hdr(pq, source_sha256=source_sha256, params=params)
    hdr.provenance["nvidia-vfx"] = version
    # 同时保留中间格式的容量字段与来源中的实际像素容量，供报告直接核验。
    hdr.provenance["content_hdr_capacity_max"] = hdr.hdr_capacity_max
    return hdr
