"""生成不依赖私人照片的最小 JPEG 结构测试夹具。"""

from __future__ import annotations

import struct


def app(marker: int, payload: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload


def minimal_jpeg(*, trailer: bytes = b"") -> bytes:
    """测试只覆盖结构扫描；有效像素解码由 Pillow 集成测试负责。"""

    return b"\xff\xd8" + app(0xDA, b"scan") + b"pixels\xff\xd9" + trailer
