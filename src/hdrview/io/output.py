"""输出目录的防覆盖与源文件隔离规则。"""

from __future__ import annotations

import os
from pathlib import Path

from hdrview.errors import OutputConflictError


def _is_link(path: Path) -> bool:
    """同时识别符号链接与 Windows 目录联接等重解析点。"""

    if path.is_symlink() or os.path.isjunction(path):
        return True
    try:
        return bool(path.stat(follow_symlinks=False).st_file_attributes & 0x400)
    except (AttributeError, FileNotFoundError):
        return False


def _resolved(path: Path) -> Path:
    """即使目标尚不存在，也按其父目录的物理位置比较路径。"""

    return path.resolve(strict=False)


def create_output_dir(root: Path | None = None, *, sources: list[Path], task: str = "general") -> Path:
    """默认进入项目 output/<task>/run-NNN，永不复用已有输出目录。"""

    if root is None:
        root = Path(__file__).resolve().parents[3] / "output" / task

    if root.exists() and (_is_link(root) or not root.is_dir()):
        raise OutputConflictError(f"输出根目录不能是链接或普通文件：{root}")

    resolved_root = _resolved(root)
    for source in sources:
        resolved_source = _resolved(source)
        if resolved_root == resolved_source or resolved_root in resolved_source.parents:
            raise OutputConflictError("输出目录不能等于源文件或包含源文件")

    root.mkdir(parents=True, exist_ok=True)
    if _is_link(root):
        raise OutputConflictError("输出根目录不能是符号链接")

    for index in range(1, 10_000):
        candidate = root / f"run-{index:03d}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise OutputConflictError(f"无法分配新的输出目录：{root}")
