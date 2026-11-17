"""复用 NVIDIA 中间结果时保留处理来源，区分历史执行与本轮执行。"""

from pathlib import Path

from hdrview.io.intermediate import intermediate_paths
from hdrview.model import HdrImage


def reused_vsr_report(hdr: HdrImage) -> dict[str, object]:
    """老文件缺少的可选字段不补造；已有参数完整保留。"""

    result = {"executed": False, "intermediate_vsr_applied": True}
    for key in ("mode", "scale", "quality", "strength", "quality_level", "input_size", "output_size", "output_transfer"):
        source_key = "vsr_" + key
        if source_key in hdr.provenance:
            result[key] = hdr.provenance[source_key]
    for key in ("source_sha256", "sdr_base_sha256"):
        if key in hdr.provenance:
            result[key] = hdr.provenance[key]
    return result


def intermediate_input_report(stem: Path) -> dict[str, str]:
    """记录实际读取的两份文件及其哈希，转换报告可独立追溯来源。"""

    from hdrview.io.source import read_source

    paths = intermediate_paths(stem)
    pixel, metadata = read_source(paths.pixel), read_source(paths.metadata)
    return {
        "pixel": str(pixel.path.resolve()), "pixel_sha256": pixel.sha256,
        "metadata": str(metadata.path.resolve()), "metadata_sha256": metadata.sha256,
    }
