"""项目内部使用的图像与容器类型；不把浮点像素等同 HDR 文件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class JpegSegment:
    marker: int
    offset: int
    length: int


@dataclass(frozen=True)
class VivoTrailer:
    info_offset: int
    data_offset: int
    info_length: int
    data_length: int
    primary_eoi_offset: int
    auxiliary_offset: int | None = None


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
    exif: dict[str, str] = field(default_factory=dict)
    vivo: VivoTrailer | None = None
    data: bytes = field(default=b"", repr=False)


@dataclass(frozen=True)
class HdrImage:
    rgba: object
    color: ColorState
    hdr_capacity_max: float
    provenance: dict[str, str | float | int | bool]


@dataclass(frozen=True)
class SdrImage:
    rgba: object
    icc: bytes | None
    compressed_jpeg: bytes | None
