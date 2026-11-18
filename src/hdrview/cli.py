"""命令行入口，负责批量读取、处理与发布结果。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hdrview.color.icc import decode_with_icc
from hdrview.errors import InvalidVivoDataError, OutputConflictError, UnsupportedImageError
from hdrview.io.intermediate import write_intermediate
from hdrview.io.inputs import jpeg_inputs
from hdrview.io.output import publish_outputs, validate_output_dir
from hdrview.io.source import assert_original_unchanged, read_source
from hdrview.nvidia.postprocess import read_truehdr_output
from hdrview.nvidia.provenance import intermediate_input_report, reused_vsr_report
from hdrview.nvidia.runtime import TrueHdrParams, run_truehdr
from hdrview.nvidia.vsr import VsrParams, run_vsr
from hdrview.output.export import DEFAULT_TARGET_NITS, SUPPORTED_TARGET_NITS, export_hdr
from hdrview.vivo.container import inspect_jpeg
from hdrview.vivo.diagnostics import analyze_file
from hdrview.vivo.fuse import reconstruct_vivo
from hdrview.vivo.metadata import parse_vivo_metadata
from hdrview.vivo.reconstruct import ReconstructionParams


def _inspect(path: Path) -> dict[str, object]:
    document = inspect_jpeg(path)
    report = {
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
    if document.vivo is not None:
        try:
            metadata = parse_vivo_metadata(document.data[document.vivo.info_offset :])
            report["vivo_max_gain_observed"] = metadata.max_gain
        except InvalidVivoDataError as error:
            report["vivo_metadata_error"] = str(error)
    return report


def _write_report(report: Path | None, payload: object) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            stream.write(encoded + "\n")
    else:
        print(encoded)


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("inputs", metavar="输入", type=Path, nargs="+", help="一个或多个 JPEG 文件或目录，目录仅读取当前层")


def _add_image_io(parser: argparse.ArgumentParser) -> None:
    _add_inputs(parser)
    parser.add_argument("-o", "--output", "--output-dir", type=Path, metavar="目录", help="直接写入此目录，默认使用当前目录下的 output/vivo 或 output/nvidia")


def _add_export_options(parser: argparse.ArgumentParser) -> None:
    """所有转换入口共用亮度默认值及允许范围，保持行为一致。"""
    _add_image_io(parser)
    parser.add_argument("--target-nits", type=int, nargs="+", default=[DEFAULT_TARGET_NITS], choices=SUPPORTED_TARGET_NITS, help="高动态范围目标显示峰值，尼特；默认仅导出 1000 尼特，400 尼特为可选项")


def _add_reconstruction_options(parser: argparse.ArgumentParser) -> None:
    """vivo 中间结果与最终转换使用同一组候选重建参数。"""
    parser.add_argument("--model", choices=["additive-residual", "ratio", "short-exposure"], default="additive-residual")
    parser.add_argument("--scale", type=float, default=4.0)
    parser.add_argument("--max-gain-cap", type=float, default=4.5)
    parser.add_argument("--highlight-threshold", type=float, default=0.02)


def _add_truehdr_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--contrast", type=int, default=100)
    parser.add_argument("--saturation", type=int, default=100)
    parser.add_argument("--middle-gray", type=int, default=50)
    parser.add_argument("--luminance", type=int, default=1000)
    parser.add_argument("--no-debanding", action="store_false", dest="debanding", help="关闭 NVIDIA TrueHDR 去色带")
    parser.set_defaults(debanding=True)


def _add_vsr_options(parser: argparse.ArgumentParser) -> None:
    """独立增强和高动态范围前处理共用可选视频超分辨率参数。"""
    parser.add_argument("--vsr-mode", choices=["upscale", "denoise", "deblur"])
    parser.add_argument("--vsr-scale", type=int, choices=[2, 3, 4], help="放大倍数，默认 2；去噪和去模糊保持原尺寸")
    parser.add_argument("--vsr-quality", choices=["low", "medium", "high", "ultra"])
    parser.add_argument("--vsr-strength", type=float, help="增强强度 [0,1]，默认 1")


def _vsr_params(args: argparse.Namespace) -> VsrParams:
    if args.vsr_mode in {"denoise", "deblur"} and args.vsr_scale is not None:
        raise ValueError("去噪和去模糊保持原尺寸，请省略 --vsr-scale")
    return VsrParams(
        args.vsr_mode or "upscale", args.vsr_scale or 2, args.vsr_quality or "high",
        1.0 if args.vsr_strength is None else args.vsr_strength,
    )


def _enhance_vsr(args: argparse.Namespace, path: Path, run_dir: Path) -> dict[str, object]:
    source = read_source(path)
    result = run_vsr(decode_with_icc(source.data), _vsr_params(args), source.sha256)
    output = run_dir / f"{path.stem}-VSR.jpg"
    output.write_bytes(result.image.compressed_jpeg)
    assert_original_unchanged(source)
    return {
        "source": str(path), "source_sha256": source.sha256,
        "pipeline": "nvidia-vsr", "gpu_executed": True, "vsr": result.report,
        "output": str(output), "output_sha256": hashlib.sha256(result.image.compressed_jpeg).hexdigest(),
    }


def _process_nvidia(args: argparse.Namespace, path: Path, run_dir: Path) -> dict[str, object]:
    source = read_source(path)
    base = None
    sdr = decode_with_icc(source.data)
    vsr_report = {"executed": False}
    if args.command == "enhance-nvidia":
        params = TrueHdrParams(args.contrast, args.saturation, args.middle_gray, args.luminance, args.debanding)
        params.validate()
        if args.vsr:
            vsr_result = run_vsr(sdr, _vsr_params(args), source.sha256)
            sdr, vsr_report = vsr_result.image, vsr_result.report
        hdr = run_truehdr(sdr, params, source.sha256)
        if args.vsr:
            # 中间结果绑定派生基础图，放大后重编码仍可核验来源和尺寸。
            hdr.provenance.update(
                vsr_applied=True, vsr_mode=vsr_report["mode"], vsr_scale=vsr_report["scale"],
                vsr_quality=vsr_report["quality"], vsr_strength=vsr_report["strength"],
                sdr_base_sha256=hashlib.sha256(sdr.compressed_jpeg).hexdigest(),
            )
            # 补充可恢复的模型和传递函数来源，兼容旧报告缺少这些字段。
            for key in ("quality_level", "output_transfer"):
                if key in vsr_report:
                    hdr.provenance["vsr_" + key] = vsr_report[key]
        gpu_executed = True
        truehdr_params = vars(params)
    else:
        intermediate_dir = args.intermediate if args.intermediate.is_dir() else None
        intermediate = intermediate_dir / f"{path.stem}-truehdr" if intermediate_dir else args.intermediate
        hdr = read_truehdr_output(intermediate, expected_source_sha256=source.sha256)
        base_hash = hdr.provenance.get("sdr_base_sha256")
        if hdr.provenance.get("vsr_applied") and not base_hash:
            raise ValueError("视频超分辨率中间结果缺少派生基础图哈希")
        if base_hash:
            base_path = args.sdr_base or intermediate_dir
            if base_path is None:
                raise ValueError("视频超分辨率中间结果需要 --sdr-base 指定派生基础图")
            if base_path.is_dir():
                base_path = base_path / f"{path.stem}-VSR-base.jpg"
            base = read_source(base_path)
            if base.sha256 != base_hash:
                raise ValueError("派生基础图 SHA-256 与中间结果不匹配")
            sdr = decode_with_icc(base.data)
            vsr_report = reused_vsr_report(hdr)
        elif args.sdr_base is not None and not args.sdr_base.is_dir():
            raise ValueError("当前中间结果未绑定派生基础图，请省略 --sdr-base")
        gpu_executed = False
        truehdr_params = {name: hdr.provenance[name] for name in ("contrast", "saturation", "middle_gray", "luminance", "debanding") if name in hdr.provenance}
    if hdr.rgba.shape != sdr.rgba.shape:
        raise ValueError("NVIDIA 中间结果与原图尺寸不匹配")
    report = {
        "source": str(path),
        "source_sha256": source.sha256,
        "pipeline": "nvidia-truehdr",
        "truehdr_params": truehdr_params,
        "gpu_executed": gpu_executed,
        "vsr": vsr_report,
    }
    if args.command == "convert-nvidia":
        report["intermediate_input"] = intermediate_input_report(intermediate)
        if "nvidia-vfx" in hdr.provenance:
            report["nvidia_vfx"] = hdr.provenance["nvidia-vfx"]
        report["content_hdr_capacity_max"] = hdr.hdr_capacity_max
    if hdr.provenance.get("sdr_base_sha256"):
        base_path = run_dir / f"{path.stem}-VSR-base.jpg"
        base_path.write_bytes(sdr.compressed_jpeg)
        report["sdr_base"] = {"path": str(base_path), "sha256": hdr.provenance["sdr_base_sha256"]}
    if gpu_executed:
        # 真实运行成功后先保留线性 HDR，再派生显示输出；报告路径可机器读取。
        intermediate = write_intermediate(hdr, run_dir / f"{path.stem}-truehdr")
        report["intermediate"] = {
            "pixel": str(intermediate.pixel),
            "metadata": str(intermediate.metadata),
            "source_sha256": source.sha256,
        }
        report["nvidia_vfx"] = hdr.provenance["nvidia-vfx"]
        report["content_hdr_capacity_max"] = hdr.hdr_capacity_max
    report["outputs"] = [export_hdr(hdr, sdr, run_dir, path.stem, nits) for nits in args.target_nits]
    assert_original_unchanged(source)
    if base is not None:
        assert_original_unchanged(base)
    return report


def _process_vivo(
    args: argparse.Namespace, path: Path, run_dir: Path, *, skip_no_gainmap: bool,
) -> dict[str, object] | None:
    source = read_source(path)
    document = inspect_jpeg(path)
    if document.vivo is None and skip_no_gainmap:
        return None
    params = ReconstructionParams(args.model, args.scale, args.max_gain_cap, args.highlight_threshold)
    result = reconstruct_vivo(document, params)
    record = {"source": str(path), **result.diagnostics, **result.image.provenance}
    if args.command == "reconstruct-vivo":
        intermediate = write_intermediate(result.image, run_dir / f"{path.stem}-vivo")
        record["intermediate"] = {"pixel": str(intermediate.pixel), "metadata": str(intermediate.metadata)}
    else:
        primary = document.data[: document.vivo.primary_eoi_offset + 2]
        sdr = decode_with_icc(primary)
        record["outputs"] = [export_hdr(result.image, sdr, run_dir, path.stem, nits) for nits in args.target_nits]
    assert_original_unchanged(source)
    return record


def _result_paths(value: object, paths: dict[str, str]) -> object:
    """报告中的产物路径指向最终目录，来源字段保留实际读取路径。"""
    if isinstance(value, dict):
        return {key: _result_paths(item, paths) for key, item in value.items()}
    if isinstance(value, list):
        return [_result_paths(item, paths) for item in value]
    if isinstance(value, str):
        return paths.get(value, value)
    return value


def _process_images(args: argparse.Namespace, paths: list[Path]) -> None:
    if not paths:
        raise FileNotFoundError("没有可处理的 JPEG 输入")
    is_vivo = args.command in {"convert-vivo", "reconstruct-vivo"}
    family = "vivo" if is_vivo else "nvidia"
    output = args.output if args.output is not None else Path.cwd() / "output" / family
    validate_output_dir(output, paths)

    report_names = set()
    for path in paths:
        report_name = f"{path.stem}-{args.command}-report.json"
        if report_name.casefold() in report_names:
            raise OutputConflictError(f"批次内有同名图片：{path}。请重命名后重试。")
        report_names.add(report_name.casefold())
        target = output / report_name
        if target.exists() or target.is_symlink():
            raise OutputConflictError(f"输出报告已存在：{target}。请指定其他输出目录。")

    if args.command == "convert-nvidia" and len(paths) > 1:
        if not args.intermediate.is_dir() or (args.sdr_base is not None and not args.sdr_base.is_dir()):
            raise ValueError("批量转换需要用 --intermediate 指定中间结果目录，--sdr-base 如提供也应为目录")

    process_nvidia = _enhance_vsr if args.command == "enhance-vsr" else _process_nvidia
    skip_no_gainmap = len(paths) > 1 or any(item.is_dir() for item in args.inputs)
    skipped = []

    # 在系统临时目录逐张编码，整批成功才发布，避免失败后留下半批结果。
    with TemporaryDirectory(prefix="hdrview-") as directory:
        staging = Path(directory)
        reports = []
        for path in paths:
            try:
                if is_vivo:
                    report = _process_vivo(args, path, staging, skip_no_gainmap=skip_no_gainmap)
                else:
                    report = process_nvidia(args, path, staging)
            except Exception as error:
                error.add_note(f"处理输入：{path}")
                raise
            if report is None:
                skipped.append(path)
                continue
            reports.append((f"{path.stem}-{args.command}-report.json", report))
        if not reports:
            raise UnsupportedImageError(f"{len(paths)} 张输入图片都没有 vivo 私有高光辅助图")
        result_paths = {str(path): str(output / path.name) for path in staging.iterdir()}
        for filename, report in reports:
            _write_report(staging / filename, _result_paths(report, result_paths))
        publish_outputs(staging, output, paths)
    for path in skipped:
        print(f"没有 vivo 私有高光辅助图，已跳过：{path}")
    print(f"已处理 {len(reports)} 张图片，输出目录：{output.resolve()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hdrview")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="只读检查 JPEG 结构")
    _add_inputs(inspect)
    inspect.add_argument("--output", type=Path)
    analyze = subparsers.add_parser("analyze-vivo", help="只读分析主辅高光关系")
    _add_inputs(analyze)
    analyze.add_argument("--output", type=Path)
    reconstruct = subparsers.add_parser("reconstruct-vivo", help="保存 vivo 辅助高光重建的中间文件")
    _add_image_io(reconstruct)
    _add_reconstruction_options(reconstruct)
    convert = subparsers.add_parser("convert-vivo", help="vivo 候选高光到标准 Ultra HDR（观感未验证）")
    _add_export_options(convert)
    _add_reconstruction_options(convert)
    nvidia = subparsers.add_parser("convert-nvidia", help="从已有 NVIDIA TrueHDR 中间结果导出图片")
    _add_export_options(nvidia)
    nvidia.add_argument("--intermediate", type=Path, required=True, help="中间文件、无扩展名的路径或含各图 -truehdr 中间文件的目录")
    nvidia.add_argument("--sdr-base", type=Path, help="视频超分辨率派生基础图或含各图 -VSR-base.jpg 的目录")
    enhance = subparsers.add_parser("enhance-nvidia", help="运行 NVIDIA TrueHDR 并导出增强图片")
    _add_export_options(enhance)
    _add_truehdr_options(enhance)
    enhance.add_argument("--vsr", action="store_true", help="先执行 NVIDIA 视频超分辨率，再执行 TrueHDR；默认关闭")
    _add_vsr_options(enhance)
    vsr_only = subparsers.add_parser("enhance-vsr", help="独立执行 NVIDIA 视频超分辨率、去噪或去模糊，输出标准动态范围 JPEG")
    _add_image_io(vsr_only)
    _add_vsr_options(vsr_only)
    verify = subparsers.add_parser("verify", help="验证已生成的 Ultra HDR 结构与参考解码")
    _add_inputs(verify)
    verify.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if hasattr(args, "target_nits"):
        # 保留用户顺序并去重，避免第二次写同名文件时失败。
        args.target_nits = list(dict.fromkeys(args.target_nits))
    if args.command == "enhance-nvidia" and not args.vsr and any(
        getattr(args, name) is not None for name in ("vsr_mode", "vsr_scale", "vsr_quality", "vsr_strength")
    ):
        parser.error("视频超分辨率参数需要同时指定 --vsr")

    # 保留输入顺序，目录内容按名称排序，重复路径只处理一次。
    paths_by_location = {}
    for item in args.inputs:
        for path in jpeg_inputs(item):
            paths_by_location.setdefault(path.resolve(), path)
    paths = list(paths_by_location.values())

    if args.command == "verify":
        from dataclasses import asdict
        from hdrview.output.ultrahdr import inspect_ultrahdr
        from hdrview.verify.roundtrip import decode_reference

        # 混合输出目录中的独立增强图和派生基础图都是标准动态范围。
        direct_inputs = {path.resolve() for path in args.inputs if not path.is_dir()}
        paths = [
            path for location, path in paths_by_location.items()
            if location in direct_inputs or not path.stem.lower().endswith(("-vsr-base", "-vsr"))
        ]
        if not paths:
            raise FileNotFoundError("没有可验证的 Ultra HDR 图片")
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

    if args.command == "inspect":
        _write_report(args.output, [_inspect(path) for path in paths])
    elif args.command == "analyze-vivo":
        reports = [analyze_file(path) for path in paths]
        _write_report(args.output, reports[0] if len(reports) == 1 else reports)
    else:
        _process_images(args, paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
