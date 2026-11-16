"""有界 JPEG marker 扫描与 vivo streaminfo/streamdata 定位。"""

from __future__ import annotations

import struct
from pathlib import Path

from hdrview.errors import InvalidJpegError
from hdrview.io.source import read_source
from hdrview.model import ImageDocument, JpegSegment, VivoTrailer

MAX_JPEG_BYTES = 256 * 1024 * 1024
MAX_SEGMENTS = 512
_INFO = b"streaminfo\x00"
_DATA = b"streamdata"
_STREAM_COUNT = b"streamcount\x00\x01vivo"


def scan_jpeg(data: bytes) -> tuple[JpegSegment, ...]:
    """扫描主 JPEG；SOS 后只把未转义的 EOI 当作主图结束。"""

    if len(data) > MAX_JPEG_BYTES or not data.startswith(b"\xff\xd8"):
        raise InvalidJpegError("输入不是受支持大小内的 JPEG")
    segments: list[JpegSegment] = []
    position = 2
    while position < len(data):
        if len(segments) >= MAX_SEGMENTS:
            raise InvalidJpegError("JPEG 段数量超出限制")
        marker_offset = position
        if data[position] != 0xFF:
            raise InvalidJpegError(f"JPEG 段在偏移 {position} 处损坏")
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            raise InvalidJpegError("JPEG 以不完整 marker 结束")
        marker = data[position]
        position += 1
        if marker == 0xD9:
            segments.append(JpegSegment(marker, marker_offset, 2))
            return tuple(segments)
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            segments.append(JpegSegment(marker, marker_offset, position - marker_offset))
            continue
        if position + 2 > len(data):
            raise InvalidJpegError("JPEG 段长度字段截断")
        length = struct.unpack_from(">H", data, position)[0]
        if length < 2 or position + length > len(data):
            raise InvalidJpegError(f"JPEG 段长度越界：{length}")
        segments.append(JpegSegment(marker, marker_offset, length + 2))
        position += length
        if marker == 0xDA:
            position = _find_eoi(data, position)
            segments.append(JpegSegment(0xD9, position, 2))
            return tuple(segments)
    raise InvalidJpegError("JPEG 缺少 EOI")


def _find_eoi(data: bytes, position: int) -> int:
    """熵编码中的 FF00 和 restart marker 不是文件结束。"""

    while position + 1 < len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        marker = data[position + 1]
        if marker == 0xD9:
            return position
        if marker in (0x00, 0xFF) or 0xD0 <= marker <= 0xD7:
            position += 2
            continue
        # 多扫描 JPEG 暂不猜测后续结构；由明确错误要求扩展支持。
        raise InvalidJpegError(f"暂不支持主扫描中的 marker 0xFF{marker:02X}")
    raise InvalidJpegError("JPEG 扫描数据缺少 EOI")


def locate_vivo_trailer(data: bytes) -> VivoTrailer | None:
    """解析实测布局：主 EOI + streamdata/JPEG + streaminfo/JSON。

    不把尾部最后一个 FFD9 当主图 EOI，因为 streaminfo 中也可能出现该字节。
    """

    primary_eoi = data.find(b"\xff\xd9streamdata", 2)
    if primary_eoi < 0:
        return None
    info_offset = data.rfind(_INFO)
    if info_offset < 0 or info_offset + 38 > len(data):
        raise InvalidJpegError("vivo streamdata 缺少完整的尾部 streaminfo")
    auxiliary_offset = primary_eoi + 2 + len(_DATA)
    if data[auxiliary_offset : auxiliary_offset + 2] != b"\xff\xd8":
        raise InvalidJpegError("vivo streamdata 载荷不是 JPEG")
    auxiliary_segments = scan_jpeg(data[auxiliary_offset:info_offset])
    auxiliary_end = auxiliary_offset + auxiliary_segments[-1].offset + 2
    if auxiliary_end != info_offset:
        raise InvalidJpegError("vivo 辅助 JPEG 与 streaminfo 之间存在未声明数据")
    if data.count(b"streamdata") != 1 or data.count(_INFO) != 1:
        raise InvalidJpegError("vivo trailer 声明重复或数量不正确")
    if _STREAM_COUNT not in data[info_offset + len(_INFO) : info_offset + 48]:
        raise InvalidJpegError("vivo streaminfo 的 streamcount/vivo 标记不匹配")
    return VivoTrailer(
        info_offset=info_offset,
        data_offset=auxiliary_offset,
        info_length=len(data) - info_offset,
        data_length=info_offset - auxiliary_offset,
        primary_eoi_offset=primary_eoi,
    )


def inspect_jpeg(path: Path) -> ImageDocument:
    """读取、扫描并保留原始字节；此函数不写任何图片。"""

    source = read_source(path)
    return ImageDocument(
        source_path=source.path,
        sha256=source.sha256,
        jpeg_segments=scan_jpeg(source.data),
        primary_icc=None,
        vivo=locate_vivo_trailer(source.data),
        data=source.data,
    )
