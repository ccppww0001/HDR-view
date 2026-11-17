"""两条增强管线共享的导出策略；与命令行参数解析分离。"""

from __future__ import annotations

from pathlib import Path

from hdrview.mapping import DisplayMapping, map_highlights
from hdrview.model import HdrImage, SdrImage
from hdrview.output.jxr import encode_jxr
from hdrview.output.ultrahdr import DEFAULT_TARGET_NITS, encode_ultrahdr

SUPPORTED_TARGET_NITS = (400, 1000)


def export_hdr(
    hdr: HdrImage, sdr: SdrImage, run_dir: Path, stem: str,
    target_nits: int = DEFAULT_TARGET_NITS,
) -> dict[str, object]:
    """默认保留 1000 尼特内容；400 尼特映射一次后共用 JPEG 与 JPEG XR。"""

    if target_nits == 400:
        content = map_highlights(hdr, DisplayMapping())
    elif target_nits == DEFAULT_TARGET_NITS:
        content = hdr
    else:
        raise ValueError("输出目标仅支持 400 或 1000 nit")
    output = run_dir / f"{stem}-UltraHDR-{target_nits}nit.jpg"
    encoded = encode_ultrahdr(content, sdr, output, target_nits=target_nits)
    record = {
        "output": str(output),
        "target_nits": target_nits,
        # 来源取自实际编码对象，1000 尼特保持原内容。
        "display_mapping": content.provenance.get("display_mapping", "none") if target_nits == 400 else "none",
        "is_ultrahdr": encoded.is_ultrahdr,
        "hdr_capacity_max": encoded.hdr_capacity_max,
        "gainmap_size": [encoded.gainmap_width, encoded.gainmap_height],
    }
    if target_nits == 400:
        jxr_path = run_dir / f"{stem}-HDR-400nit.jxr"
        jxr = encode_jxr(content, jxr_path)
        # JPEG XR 的固定容量字段不代表显示器的实际物理峰值。
        jxr.pop("hdr_capacity_max", None)
        record["jpeg_xr"] = jxr
    return record
