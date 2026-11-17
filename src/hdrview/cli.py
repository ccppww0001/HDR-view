"""命令行入口：结构检查、vivo 诊断与研究候选重建。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from hdrview.color.icc import decode_with_icc
from hdrview.io.intermediate import write_intermediate
from hdrview.io.inputs import jpeg_inputs
from hdrview.io.output import create_output_dir
from hdrview.io.source import assert_original_unchanged, read_source
from hdrview.nvidia.postprocess import read_truehdr_output
from hdrview.nvidia.provenance import intermediate_input_report, reused_vsr_report
from hdrview.nvidia.runtime import TrueHdrParams, run_truehdr
from hdrview.nvidia.vsr import VsrParams, run_vsr
from hdrview.output.export import DEFAULT_TARGET_NITS, SUPPORTED_TARGET_NITS, export_hdr
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


def _add_export_options(parser: argparse.ArgumentParser) -> None:
    """所有转换入口共用亮度默认值及允许范围，保持行为一致。"""
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
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
    _add_reconstruction_options(reconstruct)
    convert = subparsers.add_parser("convert-vivo", help="vivo 候选高光到标准 Ultra HDR（观感未验证）")
    _add_export_options(convert)
    _add_reconstruction_options(convert)
    nvidia = subparsers.add_parser("convert-nvidia", help="NVIDIA TrueHDR 中间结果到 Ultra HDR 和 JPEG XR")
    _add_export_options(nvidia)
    nvidia.add_argument("--intermediate", type=Path, required=True)
    nvidia.add_argument("--sdr-base", type=Path, help="含视频超分辨率的中间结果所对应的派生 JPEG 基础图")
    enhance = subparsers.add_parser("enhance-nvidia", help="直接运行 NVIDIA TrueHDR，再输出 Ultra HDR 和 JPEG XR")
    _add_export_options(enhance)
    _add_truehdr_options(enhance)
    enhance.add_argument("--vsr", action="store_true", help="先执行 NVIDIA 视频超分辨率，再执行 TrueHDR；默认关闭")
    _add_vsr_options(enhance)
    vsr_only = subparsers.add_parser("enhance-vsr", help="独立执行 NVIDIA 视频超分辨率、去噪或去模糊，输出标准动态范围 JPEG")
    vsr_only.add_argument("input", type=Path)
    vsr_only.add_argument("--output", type=Path)
    _add_vsr_options(vsr_only)
    verify = subparsers.add_parser("verify", help="验证已生成的 Ultra HDR 结构与参考解码")
    verify.add_argument("input", type=Path)
    verify.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if hasattr(args, "target_nits"):
        # 保留用户顺序并去重，避免第二次写同名文件时失败。
        args.target_nits = list(dict.fromkeys(args.target_nits))
    if args.command == "enhance-nvidia" and not args.vsr and any(
        getattr(args, name) is not None for name in ("vsr_mode", "vsr_scale", "vsr_quality", "vsr_strength")
    ):
        parser.error("视频超分辨率参数需要同时指定 --vsr")

    if args.command == "enhance-vsr":
        source = read_source(args.input)
        result = run_vsr(decode_with_icc(source.data), _vsr_params(args), source.sha256)
        run_dir = create_output_dir(args.output, sources=[args.input], task="vsr")
        output = run_dir / f"{args.input.stem}-VSR.jpg"
        output.write_bytes(result.image.compressed_jpeg)
        assert_original_unchanged(source)
        _write_report(run_dir / "report.json", {
            "source": str(args.input), "source_sha256": source.sha256,
            "pipeline": "nvidia-vsr", "gpu_executed": True, "vsr": result.report,
            "output": str(output), "output_sha256": hashlib.sha256(result.image.compressed_jpeg).hexdigest(),
        })
        return 0

    if args.command == "verify":
        from dataclasses import asdict
        from hdrview.output.ultrahdr import inspect_ultrahdr
        from hdrview.verify.roundtrip import decode_reference

        # 派生基础图属于标准动态范围，目录验证只排除这一明确命名的辅助文件。
        paths = [path for path in jpeg_inputs(args.input) if not path.stem.lower().endswith("-vsr-base")] if args.input.is_dir() else [args.input]
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

    if args.command in {"convert-nvidia", "enhance-nvidia"}:
        source = read_source(args.input)
        sdr = decode_with_icc(source.data)
        vsr_report = {"executed": False}
        if args.command == "enhance-nvidia":
            params = TrueHdrParams(args.contrast, args.saturation, args.middle_gray, args.luminance, args.debanding)
            params.validate()
            if args.vsr:
                vsr_result = run_vsr(sdr, _vsr_params(args), source.sha256)
                sdr, vsr_report = vsr_result.image, vsr_result.report
            # 真实 HDR 运行先于 create_output_dir；缺依赖/CUDA 时不能留下空输出目录。
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
            hdr = read_truehdr_output(args.intermediate, expected_source_sha256=source.sha256)
            base_hash = hdr.provenance.get("sdr_base_sha256")
            if hdr.provenance.get("vsr_applied") and not base_hash:
                raise ValueError("视频超分辨率中间结果缺少派生基础图哈希")
            if base_hash:
                if args.sdr_base is None:
                    raise ValueError("视频超分辨率中间结果需要 --sdr-base 指定派生基础图")
                base = read_source(args.sdr_base)
                if base.sha256 != base_hash:
                    raise ValueError("派生基础图 SHA-256 与中间结果不匹配")
                sdr = decode_with_icc(base.data)
                vsr_report = reused_vsr_report(hdr)
            elif args.sdr_base is not None:
                raise ValueError("当前中间结果未绑定派生基础图，请省略 --sdr-base")
            gpu_executed = False
            truehdr_params = {name: hdr.provenance[name] for name in ("contrast", "saturation", "middle_gray", "luminance", "debanding") if name in hdr.provenance}
        if hdr.rgba.shape != sdr.rgba.shape:
            raise ValueError("NVIDIA 中间结果与原图尺寸不匹配")
        sources = [args.input]
        if args.command == "convert-nvidia" and args.sdr_base is not None:
            sources.append(args.sdr_base)
        run_dir = create_output_dir(args.output, sources=sources, task="nvidia")
        report = {
            "source": str(args.input),
            "source_sha256": source.sha256,
            "pipeline": "nvidia-truehdr",
            "truehdr_params": truehdr_params,
            "gpu_executed": gpu_executed,
            "vsr": vsr_report,
        }
        if args.command == "convert-nvidia":
            report["intermediate_input"] = intermediate_input_report(args.intermediate)
            if "nvidia-vfx" in hdr.provenance:
                report["nvidia_vfx"] = hdr.provenance["nvidia-vfx"]
            report["content_hdr_capacity_max"] = hdr.hdr_capacity_max
        if hdr.provenance.get("sdr_base_sha256"):
            base_path = run_dir / f"{args.input.stem}-VSR-base.jpg"
            base_path.write_bytes(sdr.compressed_jpeg)
            report["sdr_base"] = {"path": str(base_path), "sha256": hdr.provenance["sdr_base_sha256"]}
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
        report["outputs"] = [export_hdr(hdr, sdr, run_dir, args.input.stem, nits) for nits in args.target_nits]
        assert_original_unchanged(source)
        if args.command == "convert-nvidia" and args.sdr_base is not None:
            assert_original_unchanged(base)
        _write_report(run_dir / "report.json", report)
        return 0

    if args.command == "inspect":
        paths = jpeg_inputs(args.input)
        _write_report(args.output, [_inspect(path) for path in paths])
        return 0
    if args.command == "analyze-vivo":
        _write_report(args.output, analyze_file(args.input))
        return 0

    paths = jpeg_inputs(args.input)
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
                record.setdefault("outputs", []).append(export_hdr(result.image, sdr, run_dir, path.stem, nits))
        assert_original_unchanged(source)
        results.append(record)
    _write_report(run_dir / "report.json", results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
