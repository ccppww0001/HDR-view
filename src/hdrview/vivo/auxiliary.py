"""辅助 JPEG 提取、EXIF/ICC 核验和首版支持范围。"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageCms, UnidentifiedImageError

from hdrview.errors import InvalidVivoDataError
from hdrview.model import ImageDocument
from hdrview.vivo.container import scan_jpeg
from hdrview.vivo.metadata import parse_vivo_metadata


@dataclass(frozen=True)
class SupportStatus:
    supported: bool
    reason: str


def extract_auxiliary_jpeg(document: ImageDocument) -> bytes:
    """仅截取 streamdata 与 streaminfo 之间经完整扫描的 JPEG。"""

    trailer = document.vivo
    if trailer is None:
        raise InvalidVivoDataError("文件不含 vivo 辅助图")
    auxiliary = document.data[trailer.data_offset : trailer.data_offset + trailer.data_length]
    segments = scan_jpeg(auxiliary)
    if segments[-1].offset + 2 != len(auxiliary):
        raise InvalidVivoDataError("辅助 JPEG 后存在未声明数据")
    return auxiliary


def _image_properties(jpeg: bytes) -> tuple[tuple[int, int], bytes | None, dict[str, str]]:
    try:
        with Image.open(BytesIO(jpeg)) as image:
            image.load()
            icc = image.info.get("icc_profile")
            if icc:
                ImageCms.ImageCmsProfile(BytesIO(icc))
            exif = image.getexif()
            fields = {"Make": str(exif.get(0x010F, "")), "Model": str(exif.get(0x0110, ""))}
            return image.size, icc, fields
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise InvalidVivoDataError("JPEG 像素或 ICC 无法安全读取") from error


def _is_display_p3(icc: bytes | None) -> bool:
    if not icc:
        return False
    profile = ImageCms.ImageCmsProfile(BytesIO(icc))
    description = ImageCms.getProfileDescription(profile).strip().lower()
    return "display p3" in description or "display-p3" in description


def classify_support(document: ImageDocument) -> SupportStatus:
    """白名单只覆盖已验证样本，不把类似厂商标签推广到其他机型。"""

    if document.vivo is None:
        return SupportStatus(False, "没有 vivo 私有高光 trailer")
    try:
        primary_size, primary_icc, exif = _image_properties(document.data[: document.vivo.primary_eoi_offset + 2])
        auxiliary = extract_auxiliary_jpeg(document)
        auxiliary_size, auxiliary_icc, _ = _image_properties(auxiliary)
        parse_vivo_metadata(document.data[document.vivo.info_offset :])
    except InvalidVivoDataError as error:
        return SupportStatus(False, f"私有数据损坏：{error}")
    if exif != {"Make": "vivo", "Model": "iQOO Neo9 Pro"}:
        return SupportStatus(False, "机型或厂商未验证，首版只支持 Neo9 Pro 当前结构")
    if primary_size != (4096, 3072) or auxiliary_size != (2048, 1536):
        return SupportStatus(False, "主图/辅助图尺寸不符合已验证结构")
    if not (_is_display_p3(primary_icc) and _is_display_p3(auxiliary_icc)):
        return SupportStatus(False, "主图和辅助图必须都具有可解析的 Display-P3 ICC")
    return SupportStatus(True, "Neo9 Pro 当前 OriginOS 样本结构已验证；高光融合语义仍需研究")
