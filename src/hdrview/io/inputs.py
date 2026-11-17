"""目录命令共用 JPEG 枚举规则，统一扩展名与大小写支持。"""

from pathlib import Path


def jpeg_inputs(path: Path) -> list[Path]:
    """单文件保持原路径；目录仅选择当前层的 JPEG 普通文件。"""

    if not path.is_dir():
        return [path]
    return sorted(
        item for item in path.iterdir()
        if item.is_file() and item.suffix.lower() in {".jpg", ".jpeg"}
    )
