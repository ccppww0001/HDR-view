"""将 vivo 候选亮度模型放入共享的线性 BT.2020 中间表示。"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageCms

from hdrview.color.gamut import rec709_to_bt2020
from hdrview.color.icc import decode_with_icc
from hdrview.color.transfer import srgb_to_linear
from hdrview.errors import UnsupportedImageError
from hdrview.model import ColorState, HdrImage, ImageDocument
from hdrview.vivo.auxiliary import classify_support, extract_auxiliary_jpeg
from hdrview.vivo.metadata import parse_vivo_metadata
from hdrview.vivo.reconstruct import ReconstructionParams, reconstruct

P3_TO_REC709 = np.array(
    [[1.22494, -0.22494, 0.0], [-0.042057, 1.042057, 0.0], [-0.019638, -0.078636, 1.098274]],
    dtype=np.float32,
)


@dataclass(frozen=True)
class ReconstructionResult:
    image: HdrImage
    diagnostics: dict[str, float | bool | str]
    xdr_appearance_verified: bool = False


def auxiliary_linear_bt2020(jpeg: bytes, size: tuple[int, int]) -> np.ndarray:
    """P3 辅助图先线性化，再转 BT.2020；不先裁到较小 sRGB 色域。"""

    with Image.open(BytesIO(jpeg)) as image:
        profile = ImageCms.ImageCmsProfile(BytesIO(image.info["icc_profile"]))
        description = ImageCms.getProfileDescription(profile).lower()
        if "display p3" not in description and "display-p3" not in description:
            raise UnsupportedImageError("辅助图必须为 Display-P3")
        encoded = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    linear = srgb_to_linear(encoded)
    rec709 = np.einsum("...c,dc->...d", linear, P3_TO_REC709)
    bt2020 = rec709_to_bt2020(rec709)
    return cv2.resize(bt2020, size, interpolation=cv2.INTER_LINEAR).astype(np.float32)


def reconstruct_vivo(document: ImageDocument, params: ReconstructionParams) -> ReconstructionResult:
    """当前仅提供证据受限的候选重建，不宣称复现手机相册的专有曲线。"""

    status = classify_support(document)
    if not status.supported:
        raise UnsupportedImageError(status.reason)
    assert document.vivo is not None
    primary_jpeg = document.data[: document.vivo.primary_eoi_offset + 2]
    sdr = decode_with_icc(primary_jpeg)
    primary_linear = rec709_to_bt2020(srgb_to_linear(sdr.rgba[..., :3].astype(np.float32) / 255))
    auxiliary = auxiliary_linear_bt2020(extract_auxiliary_jpeg(document), (sdr.rgba.shape[1], sdr.rgba.shape[0]))
    metadata = parse_vivo_metadata(document.data[document.vivo.info_offset :])
    luma = np.einsum("...c,c->...", auxiliary[..., :3], np.array([0.2627, 0.6780, 0.0593], dtype=np.float32))
    result = np.empty((*primary_linear.shape[:2], 4), dtype=np.float32)
    for channel in range(3):
        result[..., channel] = reconstruct(primary_linear[..., channel], luma, params)
    result[..., 3] = 1.0
    capacity = float(max(1.0, np.max(result[..., :3] / np.maximum(primary_linear[..., :3], 1e-8))))
    image = HdrImage(
        rgba=result,
        color=ColorState("bt2020", "linear"),
        hdr_capacity_max=capacity,
        provenance={
            "source_sha256": document.sha256,
            "pipeline": "vivo-private-highlight-candidate",
            "model": params.model,
            "scale": params.scale,
            "max_gain_cap": params.max_gain_cap,
            "highlight_threshold": params.highlight_threshold,
            "xdr_appearance_verified": False,
            "research_only": True,
        },
    )
    return ReconstructionResult(
        image=image,
        diagnostics={
            "vivo_max_gain_observed": metadata.max_gain,
            "auxiliary_luminance_max": float(np.max(luma)),
            "hdr_capacity_max_observed": capacity,
            "xdr_appearance_verified": False,
            "status": "合理 HDR 重建，手机 XDR 观感未验证",
        },
    )
