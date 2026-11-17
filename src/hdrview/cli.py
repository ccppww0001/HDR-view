"""命令行入口：结构检查、vivo 诊断与研究候选重建。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hdrview.color.icc import decode_with_icc
from hdrview.io.intermediate import write_intermediate
from hdrview.io.output import create_output_dir
from hdrview.io.source import assert_original_unchanged, read_source
from hdrview.nvidia.postprocess import read_truehdr_output
from hdrview.output.ultrahdr import encode_ultrahdr
from hdrview.vivo.container import inspect_jpeg
from hdrview.vivo.diagnostics import analyze_file
from hdrview.vivo.fuse import reconstruct_vivo
from hdrview.vivo.reconstruct import ReconstructionParams


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


def _write_report(report: Path | None, payload: object) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if report:
        if report.exists():
            raise FileExistsError(f"报告已存在：{report}")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hdrview")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="只读检查 JPEG 结构")
    inspect.add_argument("input", type=Path)
    inspect.add_argument("--report", type=Path)
    analyze = subparsers.add_parser("analyze-vivo", help="只读分析主辅高光关系")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--report", type=Path)
    reconstruct = subparsers.add_parser("reconstruct-vivo", help="生成研究候选 HDR，不宣称复现 XDR")
    reconstruct.add_argument("input", type=Path)
    reconstruct.add_argument("--output", type=Path, required=True)
    reconstruct.add_argument("--model", choices=["additive-residual", "ratio", "short-exposure"], default="additive-residual")
    reconstruct.add_argument("--scale", type=float, default=4.0)
    reconstruct.add_argument("--max-gain-cap", type=float, default=4.5)
    reconstruct.add_argument("--highlight-threshold", type=float, default=0.02)
    convert = subparsers.add_parser("convert-vivo", help="vivo 候选高光到标准 Ultra HDR（观感未验证）")
    convert.add_argument("input", type=Path)
    convert.add_argument("--output", type=Path, required=True)
    convert.add_argument("--model", choices=["additive-residual", "ratio", "short-exposure"], default="additive-residual")
    convert.add_argument("--scale", type=float, default=4.0)
    convert.add_argument("--max-gain-cap", type=float, default=4.5)
    convert.add_argument("--highlight-threshold", type=float, default=0.02)
    nvidia = subparsers.add_parser("convert-nvidia", help="ComfyUI TrueHDR 中间结果到标准 Ultra HDR")
    nvidia.add_argument("input", type=Path)
    nvidia.add_argument("--intermediate", type=Path, required=True)
    nvidia.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "convert-nvidia":
        source = read_source(args.input)
        hdr = read_truehdr_output(args.intermediate, expected_source_sha256=source.sha256)
        sdr = decode_with_icc(source.data)
        if hdr.rgba.shape != sdr.rgba.shape:
            raise ValueError("NVIDIA 中间结果与原图尺寸不匹配")
        run_dir = create_output_dir(args.output, sources=[args.input])
        output = run_dir / f"{args.input.stem}-UltraHDR.jpg"
        report = encode_ultrahdr(hdr, sdr, output)
        assert_original_unchanged(source)
        _write_report(run_dir / "report.json", {"source": str(args.input), "pipeline": "nvidia-truehdr", "output": str(output), "is_ultrahdr": report.is_ultrahdr})
        return 0

    if args.command == "inspect":
        paths = sorted(args.input.glob("*.jpg")) if args.input.is_dir() else [args.input]
        _write_report(args.report, [_inspect(path) for path in paths])
        return 0
    if args.command == "analyze-vivo":
        _write_report(args.report, analyze_file(args.input))
        return 0

    paths = sorted(args.input.glob("*.jpg")) if args.input.is_dir() else [args.input]
    if not paths:
        raise FileNotFoundError("没有可处理的 JPEG 输入")
    documents = [inspect_jpeg(path) for path in paths]
    # 先完成结构与候选重建，失败时不创建任何输出目录。
    prepared = [
        (path, document, reconstruct_vivo(document, ReconstructionParams(args.model, args.scale, args.max_gain_cap, args.highlight_threshold)))
        for path, document in zip(paths, documents)
    ]
    run_dir = create_output_dir(args.output, sources=paths)
    results = []
    for path, document, result in prepared:
        source = read_source(path)
        record = {"source": str(path), **result.diagnostics, **result.image.provenance}
        if args.command == "reconstruct-vivo":
            write_intermediate(result.image, run_dir / path.stem)
        else:
            primary = document.data[: document.vivo.primary_eoi_offset + 2]
            sdr = decode_with_icc(primary)
            output = run_dir / f"{path.stem}-UltraHDR.jpg"
            encoded = encode_ultrahdr(result.image, sdr, output)
            record.update({"output": str(output), "is_ultrahdr": encoded.is_ultrahdr, "gainmap_size": [encoded.gainmap_width, encoded.gainmap_height]})
        assert_original_unchanged(source)
        results.append(record)
    _write_report(run_dir / "report.json", results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
