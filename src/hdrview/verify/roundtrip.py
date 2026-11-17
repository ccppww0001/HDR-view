"""官方 libultrahdr 参考解码和 SDR/HDR 对照。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

from hdrview.io.intermediate import read_intermediate
from hdrview.model import HdrImage
from hdrview.output.ultrahdr import default_bridge


def decode_reference(path: Path, display_boost: float) -> HdrImage:
    """以明确的显示余量解码，不把输出张量本身当显示器实测。"""

    with tempfile.TemporaryDirectory(prefix="hdrview-decode-") as directory:
        stem = Path(directory) / "decoded"
        result = subprocess.run(
            [str(default_bridge()), "decode", "--input", str(path), "--raw", str(stem.with_suffix('.f16rgba')),
             "--meta", str(stem.with_suffix('.json')), "--boost", str(display_boost)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Ultra HDR 参考解码失败：{result.stderr.strip()}")
        return read_intermediate(stem)
