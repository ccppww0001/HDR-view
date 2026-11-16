"""使用嵌入 ICC 的 JPEG 解码；普通 convert('RGB') 不进行色彩管理。"""

from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image, ImageCms

from hdrview.model import SdrImage


def decode_with_icc(jpeg: bytes) -> SdrImage:
    """Display-P3 等嵌入配置经 LittleCMS 转换到标准 sRGB。"""

    with Image.open(BytesIO(jpeg)) as image:
        image.load()
        icc = image.info.get("icc_profile")
        if icc:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(icc))
            target_profile = ImageCms.createProfile("sRGB")
            image = ImageCms.profileToProfile(image, source_profile, target_profile, outputMode="RGB")
        else:
            # 无配置的旧式 JPEG 按惯例是 sRGB，报告输出仍显式携带配置。
            image = image.convert("RGB")
    rgba = np.empty((*image.size[::-1], 4), dtype=np.uint8)
    rgba[..., :3] = np.asarray(image, dtype=np.uint8)
    rgba[..., 3] = 255
    output_icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    return SdrImage(rgba=rgba, icc=output_icc, compressed_jpeg=jpeg)
