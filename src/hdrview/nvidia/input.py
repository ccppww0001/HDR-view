"""生成 ComfyUI 输入的标准 sRGB PNG，并提供源图 SHA-256 供工作流绑定。"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

from PIL import Image

from hdrview.color.icc import decode_with_icc


def write_srgb_png(source: Path, destination: Path) -> str:
    """输出新 PNG，返回原图哈希；不覆盖已有输入或原图。"""

    if destination.exists():
        raise FileExistsError(destination)
    decoded = decode_with_icc(source.read_bytes())
    image = Image.fromarray(decoded.rgba[..., :3], "RGB")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", icc_profile=decoded.icc)
    return sha256(source.read_bytes()).hexdigest()
