"""命令行入口：目前仅提供只读 JPEG 结构检查。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hdrview.vivo.container import inspect_jpeg


def _inspect(path: Path) -> dict[str, object]:
    document = inspect_jpeg(path)
    return {
        "path": str(document.source_path),
        "sha256": document.sha256,
        "vivo": document.vivo is not None,
        "primary_eoi_offset": document.jpeg_segments[-1].offset,
        "auxiliary_jpeg_size": document.vivo.data_length if document.vivo else None,
        "segments": [
            {"marker": f"0xFF{item.marker:02X}", "offset": item.offset, "length": item.length}
            for item in document.jpeg_segments
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hdrview")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="只读检查 JPEG 结构")
    inspect.add_argument("input", type=Path)
    inspect.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    paths = sorted(args.input.glob("*.jpg")) if args.input.is_dir() else [args.input]
    report = [_inspect(path) for path in paths]
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
