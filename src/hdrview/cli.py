"""命令行入口：结构检查、vivo 诊断与研究候选重建。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hdrview.color.icc import decode_with_icc
from hdrview.io.intermediate import write_intermediate
from hdrview.io.output import create_output_dir
from hdrview.io.source import assert_original_unchanged, read_source
from hdrview.mapping import DisplayMapping, map_highlights
from hdrview.model import HdrImage, SdrImage
from hdrview.nvidia.postprocess import read_truehdr_output
from hdrview.nvidia.runtime import TrueHdrParams, run_truehdr
from hdrview.output.jxr import encode_jxr
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


def _export_hdr(hdr: HdrImage, sdr: SdrImage, run_dir: Path, stem: str, target_nits: int) -> dict[str, object]:
    """共享编码出口：HDR400 内容只映射一次，JPEG 与 JPEG XR 使用同一像素。"""
    if target_nits == 400:
        content = map_highlights(hdr, DisplayMapping())
    elif target_nits == 1000:
        content = hdr
    else:
        raise ValueError("输出目标仅支持 400 或 1000 nit")
    output = run_dir / f"{stem}-UltraHDR-{target_nits}nit.jpg"
    encoded = encode_ultrahdr(content, sdr, output, target_nits=target_nits)
    record = {
        "output": str(output),
        "target_nits": target_nits,
        # 内容映射的来源必须来自实际编码对象，而不是根据参数伪造。
        "display_mapping": content.provenance.get("display_mapping", "none") if target_nits == 400 else "none",
        "is_ultrahdr": encoded.is_ultrahdr,
        "hdr_capacity_max": encoded.hdr_capacity_max,
        "gainmap_size": [encoded.gainmap_width, encoded.gainmap_height],
    }
    if target_nits == 400:
        jxr_path = run_dir / f"{stem}-HDR-400nit.jxr"
        jxr = encode_jxr(content, jxr_path)
        # JPEG XR 的固定 scRGB 容量字段不代表现实显示器的绝对物理峰值。
        jxr.pop("hdr_capacity_max", None)
        record["jpeg_xr"] = jxr
    return record


def _add_export_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target-nits", type=int, nargs="+", default=[400, 1000], choices=[400, 1000], help="HDR 目标显示峰值，nit；默认导出 400/1000 两份")


def _add_truehdr_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--contrast", type=int, default=100)
    parser.add_argument("--saturation", type=int, default=100)
    parser.add_argument("--middle-gray", type=int, default=50)
    parser.add_argument("--luminance", type=int, default=1000)
    parser.add_argument("--no-debanding", action="store_false", dest="debanding", help="关闭 NVIDIA TrueHDR 去色带")
    parser.set_defaults(debanding=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hdrview")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="只读检查 JPEG 结构")
    inspect.add_argument("input", type=Path)
    inspect.add_argument("--output", type=Path)
    analyze = subparsers.add_parser("analyze-vivo", help="只读分析主辅高光关系")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--output", type=Path)
    reconstruct = subparsers.add_parser("reconstruct-vivo", help="生成研究候选 HDR，不宣称复现 XDR")
    reconstruct.add_argument("input", type=Path)
    reconstruct.add_argument("--output", type=Path)
    reconstruct.add_argument("--model", choices=["additive-residual", "ratio", "short-exposure"], default="additive-residual")
    reconstruct.add_argument("--scale", type=float, default=4.0)
    reconstruct.add_argument("--max-gain-cap", type=float, default=4.5)
    reconstruct.add_argument("--highlight-threshold", type=float, default=0.02)
    convert = subparsers.add_parser("convert-vivo", help="vivo 候选高光到标准 Ultra HDR（观感未验证）")
    convert.add_argument("input", type=Path)
    convert.add_argument("--output", type=Path)
    convert.add_argument("--model", choices=["additive-residual", "ratio", "short-exposure"], default="additive-residual")
    convert.add_argument("--scale", type=float, default=4.0)
    convert.add_argument("--max-gain-cap", type=float, default=4.5)
    convert.add_argument("--highlight-threshold", type=float, default=0.02)
    convert.add_argument("--target-nits", type=int, nargs="+", default=[400, 1000], help="Ultra HDR 完整应用的显示峰值，nit；默认导出 400/1000 两份")
    nvidia = subparsers.add_parser("convert-nvidia", help="NVIDIA TrueHDR 中间结果到 Ultra HDR 和 JPEG XR")
    _add_export_options(nvidia)
    nvidia.add_argument("--intermediate", type=Path, required=True)
    enhance = subparsers.add_parser("enhance-nvidia", help="直接运行 NVIDIA TrueHDR，再输出 Ultra HDR 和 JPEG XR")
    _add_export_options(enhance)
    _add_truehdr_options(enhance)
    verify = subparsers.add_parser("verify", help="验证已生成的 Ultra HDR 结构与参考解码")
    verify.add_argument("input", type=Path)
    verify.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    if args.command == "verify":
        from dataclasses import asdict
        from hdrview.output.ultrahdr import inspect_ultrahdr
        from hdrview.verify.roundtrip import decode_reference

        paths = sorted(args.input.glob("*.jpg")) if args.input.is_dir() else [args.input]
        reports = []
        for path in paths:
            report = inspect_ultrahdr(path)
            sdr = decode_reference(path, 1.0)
            hdr = decode_reference(path, report.hdr_capacity_max)
            encoded = asdict(report)
            # 报告只写结构与解码形状，绝不把原始像素数组序列化到 JSON。
            encoded.pop("base_pixels", None)
            encoded.pop("gain_pixels", None)
            reports.append({**encoded, "output": str(path), "sdr_shape": list(sdr.rgba.shape), "hdr_shape": list(hdr.rgba.shape)})
        _write_report(args.json, reports)
        return 0

    if args.command in {"convert-nvidia", "enhance-nvidia"}:
        source = read_source(args.input)
        sdr = decode_with_icc(source.data)
        if args.command == "enhance-nvidia":
            params = TrueHdrParams(args.contrast, args.saturation, args.middle_gray, args.luminance, args.debanding)
            # 真实 HDR 运行先于 create_output_dir；缺依赖/CUDA 时不能留下空输出目录。
            hdr = run_truehdr(sdr, params, source.sha256)
            gpu_executed = True
            truehdr_params = vars(params)
        else:
            hdr = read_truehdr_output(args.intermediate, expected_source_sha256=source.sha256)
            gpu_executed = False
            truehdr_params = {name: hdr.provenance[name] for name in ("contrast", "saturation", "middle_gray", "luminance", "debanding") if name in hdr.provenance}
        if hdr.rgba.shape != sdr.rgba.shape:
            raise ValueError("NVIDIA 中间结果与原图尺寸不匹配")
        run_dir = create_output_dir(args.output, sources=[args.input], task="nvidia")
        report = {
            "source": str(args.input),
            "source_sha256": source.sha256,
            "pipeline": "nvidia-truehdr",
            "truehdr_params": truehdr_params,
            "gpu_executed": gpu_executed,
        }
        if gpu_executed:
            # 真实运行成功后先保留线性 HDR，再派生显示输出；报告路径可机器读取。
            intermediate = write_intermediate(hdr, run_dir / f"{args.input.stem}-truehdr")
            report["intermediate"] = {
                "pixel": str(intermediate.pixel),
                "metadata": str(intermediate.metadata),
                "source_sha256": source.sha256,
            }
            report["nvidia_vfx"] = hdr.provenance["nvidia-vfx"]
            report["content_hdr_capacity_max"] = hdr.hdr_capacity_max
        report["outputs"] = [_export_hdr(hdr, sdr, run_dir, args.input.stem, nits) for nits in args.target_nits]
        assert_original_unchanged(source)
        _write_report(run_dir / "report.json", report)
        return 0

    if args.command == "inspect":
        paths = sorted(args.input.glob("*.jpg")) if args.input.is_dir() else [args.input]
        _write_report(args.output, [_inspect(path) for path in paths])
        return 0
    if args.command == "analyze-vivo":
        _write_report(args.output, analyze_file(args.input))
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
    run_dir = create_output_dir(args.output, sources=paths, task="vivo" if args.command == "convert-vivo" else "vivo-intermediate")
    results = []
    for path, document, result in prepared:
        source = read_source(path)
        record = {"source": str(path), **result.diagnostics, **result.image.provenance}
        if args.command == "reconstruct-vivo":
            write_intermediate(result.image, run_dir / path.stem)
        else:
            primary = document.data[: document.vivo.primary_eoi_offset + 2]
            sdr = decode_with_icc(primary)
            for nits in args.target_nits:
                record.setdefault("outputs", []).append(_export_hdr(result.image, sdr, run_dir, path.stem, nits))
        assert_original_unchanged(source)
        results.append(record)
    _write_report(run_dir / "report.json", results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
