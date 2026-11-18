"""Windows 单文件发行版入口，必要时调用单独安装的 NVIDIA 环境。"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import subprocess
import sys

from hdrview.cli import main
from hdrview.errors import HdrViewError


def run() -> int:
    args = sys.argv[1:]
    bundle = Path(sys._MEIPASS)
    if args == ["--licenses"]:
        for notice in sorted((bundle / "licenses").rglob("*")):
            if notice.is_file():
                print(f"\n{notice.relative_to(bundle / 'licenses')}\n")
                print(notice.read_text(encoding="utf-8", errors="replace"))
        return 0

    try:
        if args and args[0] in {"enhance-nvidia", "enhance-vsr"} and not {"-h", "--help"}.intersection(args):
            location = os.environ.get("HDRVIEW_NVIDIA_PYTHON")
            if not location or not Path(location).is_absolute() or not Path(location).is_file():
                raise ValueError("请将 HDRVIEW_NVIDIA_PYTHON 设置为 NVIDIA 环境中 python.exe 的完整路径")

            # 冻结程序的 DLL 搜索目录仅用于自身，外部 Python 应使用其环境中的运行库。
            if not ctypes.windll.kernel32.SetDllDirectoryW(None):
                raise ctypes.WinError()
            launch = "import sys; sys.path.insert(0, sys.argv.pop(1)); from hdrview.release import _run_cli; _run_cli()"
            return subprocess.call([location, "-I", "-B", "-X", "utf8", "-c", launch, str(bundle / "source"), *args])
        return main(args)
    except (HdrViewError, OSError, RuntimeError, ValueError) as error:
        return _report_error(error)


def _report_error(error: Exception) -> int:
    print(f"错误：{error}", file=sys.stderr)
    for note in getattr(error, "__notes__", ()):
        print(note, file=sys.stderr)
    return 1


def _run_cli() -> None:
    """在独立的 Python 环境中运行同版本的命令入口。"""
    try:
        result = main()
    except (HdrViewError, OSError, RuntimeError, ValueError) as error:
        result = _report_error(error)
    raise SystemExit(result)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(run())
