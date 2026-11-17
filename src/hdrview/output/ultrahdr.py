"""调用本地官方 libultrahdr 薄桥接，不在 Python 中手写 MPF。"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import json
import subprocess
from dataclasses import dataclass
import tempfile

from PIL import Image

from hdrview.io.intermediate import write_intermediate
from hdrview.model import HdrImage, SdrImage

DEFAULT_TARGET_NITS = 1000


@dataclass(frozen=True)
class EncodeReport:
    output: Path
    is_ultrahdr: bool
    width: int
    height: int
    gainmap_width: int
    gainmap_height: int
    hdr_capacity_max: float
    hdr_capacity_min: float
    base_pixels: np.ndarray
    gain_pixels: np.ndarray


def encode_with_bridge(executable: Path, hdr: Path, metadata: Path, sdr: Path, output: Path, target_nits: int = DEFAULT_TARGET_NITS) -> None:
    """API-3 编码；先验证所有输入和输出冲突，再调用本机程序。"""

    for path in (executable, hdr, metadata, sdr):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output.exists():
        raise FileExistsError(f"Ultra HDR 输出已存在：{output}")
    if output.suffix.lower() not in (".jpg", ".jpeg"):
        raise ValueError("Ultra HDR 输出扩展名必须为 .jpg/.jpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(executable), "encode", "--hdr", str(hdr), "--meta", str(metadata), "--sdr", str(sdr), "--output", str(output), "--target-nits", str(target_nits)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"libultrahdr 编码失败（{result.returncode}）：{result.stderr.strip()}")
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("libultrahdr 未生成非空输出")


def default_bridge() -> Path:
    return Path(__file__).resolve().parents[1] / "native" / "build" / "Release" / "hdrview-ultrahdr.exe"


def inspect_ultrahdr(path: Path, workdir: Path | None = None) -> EncodeReport:
    """使用官方 probe 和 base/gain 图像检查，而非只看一个 XMP 字符串。"""

    with tempfile.TemporaryDirectory(prefix="hdrview-inspect-") as temporary:
        if workdir is None:
            workdir = Path(temporary)
        report_path = workdir / (path.stem + "-inspect.json")
        if report_path.exists():
            raise FileExistsError(report_path)
        result = subprocess.run(
            [str(default_bridge()), "inspect", "--input", str(path), "--json", str(report_path)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Ultra HDR 检查失败：{result.stderr.strip()}")
        data = json.loads(report_path.read_text(encoding="utf-8"))
        base = report_path.with_name(report_path.name + ".base.jpg")
        gain = report_path.with_name(report_path.name + ".gain.jpg")
        for jpeg in (base, gain):
            with Image.open(jpeg) as image:
                image.load()
                if image.width < 1 or image.height < 1:
                    raise RuntimeError("Ultra HDR 图像尺寸无效")
        if not data["is_ultrahdr"] or data["gainmap_width"] <= 0:
            raise RuntimeError("官方解码器未确认完整 Ultra HDR")
        with Image.open(base) as image:
            base_pixels = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
        with Image.open(gain) as image:
            gain_pixels = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
        return EncodeReport(output=path, **data, base_pixels=base_pixels, gain_pixels=gain_pixels)


def encode_ultrahdr(hdr: HdrImage, sdr: SdrImage, output: Path, *, target_nits: int = DEFAULT_TARGET_NITS) -> EncodeReport:
    """统一出口：增益来自 HDR/SDR，target_nits 控制完整应用的显示容量。"""

    if target_nits < 203 or target_nits > 10000:
        raise ValueError("Ultra HDR 目标峰值必须在 203–10000 nit")

    if hdr.rgba.shape != sdr.rgba.shape:
        raise ValueError("HDR 与 SDR 的尺寸/形状必须一致")
    if not sdr.compressed_jpeg:
        raise ValueError("API-3 需要原始压缩 SDR JPEG")
    # 在写入磁盘前完成中间模型验证，错误数据不能进入 C++ 桥接。
    from hdrview.io.intermediate import _validate
    _validate(hdr)
    with tempfile.TemporaryDirectory(prefix="hdrview-encode-") as directory:
        root = Path(directory)
        intermediate = write_intermediate(hdr, root / "hdr")
        source = root / "base.jpg"
        source.write_bytes(sdr.compressed_jpeg)
        encode_with_bridge(default_bridge(), intermediate.pixel, intermediate.metadata, source, output, target_nits)
        return inspect_ultrahdr(output, root)
