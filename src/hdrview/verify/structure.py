"""标准 Ultra HDR 的结构验证入口。"""

from pathlib import Path

from hdrview.output.ultrahdr import EncodeReport, inspect_ultrahdr


def verify_structure(path: Path) -> EncodeReport:
    """由官方库同时确认主图、增益图与元数据。"""

    return inspect_ultrahdr(path)
