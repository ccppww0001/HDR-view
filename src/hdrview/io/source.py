"""只读输入：一次读取并记录源文件的密码学校验值。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from hdrview.errors import SourceChangedError


@dataclass(frozen=True)
class SourceBytes:
    """原始输入的不可变快照；后续解析不再次猜测输入路径。"""

    path: Path
    data: bytes
    sha256: str


def read_source(path: Path) -> SourceBytes:
    """读取原始字节；文件保持原样，路径不用于自动输出。"""

    if path.is_dir():
        raise IsADirectoryError(f"输入必须是文件而不是目录：{path}")
    data = path.read_bytes()
    return SourceBytes(path=path, data=data, sha256=sha256(data).hexdigest())


def assert_original_unchanged(source: SourceBytes) -> None:
    """在交付前重新校验源文件，防止外部程序在处理期间修改它。"""

    if sha256(source.path.read_bytes()).hexdigest() != source.sha256:
        raise SourceChangedError(f"源文件在处理期间发生变化：{source.path}")
