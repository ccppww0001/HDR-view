"""输出目录的防覆盖与源文件隔离规则。"""

from __future__ import annotations

import os
from pathlib import Path
from shutil import copyfileobj

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


def validate_output_dir(root: Path, sources: list[Path]) -> None:
    """允许复用输出目录，仍隔离原图并拒绝链接目录。"""

    if _is_link(root) or (root.exists() and not root.is_dir()):
        raise OutputConflictError(f"输出根目录不能是链接或普通文件：{root}")

    resolved_root = _resolved(root)
    for source in sources:
        resolved_source = _resolved(source)
        if resolved_root == resolved_source or resolved_root in resolved_source.parents:
            raise OutputConflictError("输出目录不能等于源文件或包含源文件")


def publish_outputs(staging: Path, root: Path, sources: list[Path]) -> None:
    """编码完成后发布整批文件，任何发布失败都撤回本次创建的文件。"""

    validate_output_dir(root, sources)
    files = sorted(staging.iterdir(), key=lambda path: (path.name.endswith("-report.json"), path.name.casefold()))
    for path in files:
        target = root / path.name
        if target.exists() or _is_link(target):
            raise OutputConflictError(f"输出文件已存在：{target}。请指定其他输出目录。")
    root.mkdir(parents=True, exist_ok=True)
    validate_output_dir(root, sources)
    published = []
    try:
        for path in files:
            target = root / path.name
            # 独占创建，避免两个进程在检查之后同时写入同名文件。
            with path.open("rb") as source, target.open("xb") as destination:
                published.append(target)
                copyfileobj(source, destination)
    except BaseException:
        for target in reversed(published):
            target.unlink()
        raise
