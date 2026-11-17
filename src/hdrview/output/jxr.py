"""Windows WIC 原生 JPEG XR 浮点输出；不声称 Photos HDR 显示已验证。"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from hdrview.color.gamut import REC709_TO_BT2020
from hdrview.io.intermediate import _validate, write_intermediate
from hdrview.model import ColorState, HdrImage


def default_bridge() -> Path:
    return Path(__file__).resolve().parents[1] / "native" / "build" / "Release" / "hdrview-jxr.exe"


def _scrgba_to_hdr(scrgba: np.ndarray, metadata: dict) -> HdrImage:
    """显式把 Rec.709 scRGB/80-nit 转回共享 BT.2020/203-nit 模型。"""

    linear_rec709 = np.asarray(scrgba[..., :3], dtype=np.float32) * np.float32(80.0 / 203.0)
    rgb_bt2020 = np.einsum("...c,dc->...d", linear_rec709, REC709_TO_BT2020).astype(np.float32)
    if not np.all(np.isfinite(rgb_bt2020)) or np.any(rgb_bt2020 < -0.01):
        raise RuntimeError("JPEG XR 色彩转换产生无效 BT.2020 像素")
    rgba = np.concatenate((rgb_bt2020, np.asarray(scrgba[..., 3:4], dtype=np.float32)), axis=2)
    provenance = dict(metadata["provenance"])
    provenance["native_pixel_format"] = metadata["native_pixel_format"]
    provenance["native_content_max"] = float(metadata["native_content_max"])
    provenance["windows_photos_hdr_verified"] = False
    return HdrImage(
        rgba=rgba,
        color=ColorState("bt2020", "linear", 203.0),
        hdr_capacity_max=1.0,
        provenance=provenance,
    )


def _read_decode_outputs(stem: Path) -> tuple[HdrImage, dict]:
    metadata_path = stem.with_suffix(".json")
    raw_path = stem.with_suffix(".f16rgba")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected = {
        "schema": 1,
        "channels": 4,
        "pixel_format": "rgba-float16",
        "primaries": "rec709",
        "transfer": "linear",
        "sdr_white_nits": 80.0,
        "hdr_capacity_max": 1.0,
        "native_float": True,
        "native_pixel_format": "GUID_WICPixelFormat64bppRGBAHalf",
        "windows_photos_hdr_verified": False,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise RuntimeError("JPEG XR 解码 sidecar 不符合原生 scRGB float16 契约")
    width, height = metadata.get("width"), metadata.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or not (1 <= width <= 16384 and 1 <= height <= 16384):
        raise RuntimeError("JPEG XR 解码尺寸无效")
    if metadata.get("byte_stride") != width * 8:
        raise RuntimeError("JPEG XR 解码 stride 无效")
    raw = raw_path.read_bytes()
    if len(raw) != width * height * 8:
        raise RuntimeError("JPEG XR 解码像素字节数不匹配")
    scrgba = np.frombuffer(raw, dtype="<f2").reshape(height, width, 4).astype(np.float32)
    if not np.all(np.isfinite(scrgba)) or np.any(scrgba[..., 3] < 0) or not np.array_equal(scrgba[..., 3], np.ones((height, width), dtype=np.float32)):
        raise RuntimeError("JPEG XR 解码像素无效")
    content_max = metadata.get("native_content_max")
    if not isinstance(content_max, (int, float)) or not math.isfinite(content_max) or content_max < 0:
        raise RuntimeError("JPEG XR 原生内容峰值无效")
    # 峰值必须来自原生解码像素，不能相信任意 sidecar 数值。
    if not math.isclose(content_max, float(np.max(scrgba[..., :3])), rel_tol=1e-6, abs_tol=1e-6):
        raise RuntimeError("JPEG XR sidecar 峰值与实际像素不一致")
    return _scrgba_to_hdr(scrgba, metadata), metadata


def decode_jxr(input_path: Path, *, executable: Path | None = None) -> HdrImage:
    """用同一 Windows WIC 解码，并显式转换到 BT.2020/203-nit。"""

    input_path = Path(input_path)
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    bridge = executable or default_bridge()
    if not bridge.is_file():
        raise FileNotFoundError(bridge)
    with tempfile.TemporaryDirectory(prefix="hdrview-jxr-decode-") as directory:
        stem = Path(directory) / "decoded"
        result = subprocess.run(
            [str(bridge), "decode", "--input", str(input_path), "--raw", str(stem.with_suffix(".f16rgba")), "--meta", str(stem.with_suffix(".json"))],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Windows WIC JPEG XR 解码失败（{result.returncode}）：{result.stderr.strip()}")
        image, metadata = _read_decode_outputs(stem)
        expected_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
        if metadata["provenance"].get("source_sha256") != expected_hash:
            raise RuntimeError("JPEG XR 解码来源 SHA-256 不匹配")
        return image


def encode_jxr(hdr: HdrImage, output: Path, *, executable: Path | None = None) -> dict:
    """编码后用 WIC 原生 float16 回读，返回可机器读取的尺寸、峰值和验证边界。"""

    output = Path(output)
    if output.exists():
        raise FileExistsError(f"JPEG XR 输出已存在：{output}")
    if output.suffix.lower() not in (".jxr", ".wdp", ".hdp"):
        raise ValueError("JPEG XR 输出扩展名必须为 .jxr/.wdp/.hdp")
    bridge = executable or default_bridge()
    if not bridge.is_file():
        raise FileNotFoundError(bridge)
    _validate(hdr)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hdrview-jxr-encode-") as directory:
        intermediate = write_intermediate(hdr, Path(directory) / "hdr")
        result = subprocess.run(
            [str(bridge), "encode", "--hdr", str(intermediate.pixel), "--meta", str(intermediate.metadata), "--output", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Windows WIC JPEG XR 编码失败（{result.returncode}）：{result.stderr.strip()}")
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("Windows WIC 未生成非空 JPEG XR 输出")

    decoded = decode_jxr(output, executable=bridge)
    native_max = float(decoded.provenance["native_content_max"])
    return {
        "output": str(output),
        "width": int(decoded.rgba.shape[1]),
        "height": int(decoded.rgba.shape[0]),
        "native_float": True,
        "native_pixel_format": "GUID_WICPixelFormat64bppRGBAHalf",
        "native_content_max": native_max,
        "content_max_bt2020": float(np.max(decoded.rgba[..., :3])),
        "hdr_capacity_max": 1.0,
        "windows_photos_hdr_verified": False,
        # 此处哈希来自 JPEG XR 文件字节；顶层 source_sha256 保留给原始照片。
        "jxr_sha256": decoded.provenance["source_sha256"],
    }
