"""可选 NVIDIA 超分辨率、去噪与去模糊；输出独立的标准动态范围基础图。"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image, ImageCms

from hdrview.color.icc import decode_with_icc
from hdrview.color.transfer import linear_to_srgb
from hdrview.model import SdrImage
from hdrview.nvidia import runtime
from hdrview.nvidia.preprocess import prepare_truehdr_input


@dataclass(frozen=True)
class VsrParams:
    """质量名称映射官方模型；同尺寸模式保持输入分辨率。"""

    mode: str = "upscale"
    scale: int = 2
    quality: str = "high"
    strength: float = 1.0

    def output_size(self, width: int, height: int) -> tuple[int, int]:
        if self.mode not in {"upscale", "denoise", "deblur"}:
            raise ValueError("视频超分辨率模式必须为 upscale、denoise 或 deblur")
        if self.quality not in {"low", "medium", "high", "ultra"}:
            raise ValueError("视频超分辨率质量必须为 low、medium、high 或 ultra")
        if isinstance(self.scale, bool) or not isinstance(self.scale, int) or self.scale not in {2, 3, 4}:
            raise ValueError("视频超分辨率放大倍数必须为 2、3 或 4")
        if isinstance(self.strength, bool) or not isinstance(self.strength, (int, float)) or not np.isfinite(self.strength) or not 0 <= self.strength <= 1:
            raise ValueError("视频超分辨率强度必须是 [0,1] 内的有限数值")
        factor = self.scale if self.mode == "upscale" else 1
        out_width, out_height = width * factor, height * factor
        if min(width, height) < 1 or max(out_width, out_height) > 16384 or out_width * out_height > 128 * 1024 * 1024:
            raise ValueError("视频超分辨率输出超出 16384 像素边长或 128 Mi 像素预算")
        return out_width, out_height

    @property
    def quality_name(self) -> str:
        prefix = {"upscale": "", "denoise": "DENOISE_", "deblur": "DEBLUR_"}[self.mode]
        return prefix + self.quality.upper()


@dataclass(frozen=True)
class VsrResult:
    image: SdrImage
    report: dict[str, object]


def _encode_sdr(rgb_gamma22: np.ndarray) -> SdrImage:
    """模型输出回到 sRGB，保存为派生 JPEG 并回读，确保基础图与推理输入一致。"""

    # 原生滤波可能产生边界过冲，落入标准动态范围文件前显式限制到合法范围。
    encoded = linear_to_srgb(np.clip(rgb_gamma22, 0, 1) ** np.float32(2.2))
    pixels = np.rint(encoded * 255).astype(np.uint8)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    buffer = BytesIO()
    Image.fromarray(pixels).save(buffer, "JPEG", quality=95, subsampling=0, icc_profile=profile)
    return decode_with_icc(buffer.getvalue())


def run_vsr(sdr: SdrImage, params: VsrParams, source_sha256: str) -> VsrResult:
    """调用官方 VideoSuperRes，关闭模型后返回可编码且与原图绑定的结果。"""

    runtime._validate_source_sha256(source_sha256)
    rgb = prepare_truehdr_input(sdr)
    height, width = rgb.shape[:2]
    out_width, out_height = params.output_size(width, height)
    torch, nvvfx = runtime._import_runtime()
    version = runtime._version(nvvfx)
    if version != "0.2.0.0":
        raise RuntimeError(f"nvidia-vfx 版本必须为 0.2.0.0，实际为 {version}")
    runtime._check_nvidia_cuda(torch)
    try:
        quality = getattr(nvvfx.QualityLevel, params.quality_name)
        # 先配置输出尺寸再加载；整个阶段使用官方默认 CUDA 流。
        with torch.cuda.device(0), nvvfx.VideoSuperRes(quality=quality, strength=params.strength, device=0) as model:
            model.output_width, model.output_height = out_width, out_height
            model.load()
            tensor = torch.from_numpy(rgb).permute(2, 0, 1).contiguous().to(device="cuda:0", dtype=torch.float32)
            output = torch.from_dlpack(model.run(tensor, stream_ptr=0).image).clone()
            if tuple(output.shape) != (3, out_height, out_width) or output.dtype != torch.float32:
                raise RuntimeError("NVIDIA 视频超分辨率输出尺寸或 float32 数据类型不匹配")
            result = output.permute(1, 2, 0).contiguous().cpu().numpy()
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError("NVIDIA 视频超分辨率执行失败") from error
    if not np.all(np.isfinite(result)):
        raise RuntimeError("NVIDIA 视频超分辨率输出存在非有限数值")
    report = {
        "executed": True, "source_sha256": source_sha256, "nvidia_vfx": version,
        "mode": params.mode, "scale": params.scale if params.mode == "upscale" else 1,
        "quality": params.quality, "quality_level": params.quality_name, "strength": params.strength,
        "input_size": [width, height], "output_size": [out_width, out_height],
        "out_of_range_fraction": float(np.mean((result < 0) | (result > 1))),
        "output_transfer": "srgb",
    }
    return VsrResult(_encode_sdr(result), report)
