"""可选的 10-bit AVIF PQ 诊断输出，不是 Ultra HDR 替代品。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from hdrview.model import HdrImage


def save_avif_pq(hdr: HdrImage, path: Path, *, peak_nits: int) -> None:
    """通过 PyAV/SVT-AV1 写入 BT.2020/PQ，不注入伪造的 HDR10 母版元数据。"""

    if peak_nits < 203 or peak_nits > 10000:
        raise ValueError("AVIF PQ 峰值必须在 203–10000 nit")
    if path.exists():
        raise FileExistsError(path)
    try:
        import av
    except ImportError as error:
        raise RuntimeError("AVIF 诊断输出需要独立安装带 SVT-AV1 的 PyAV/FFmpeg 环境") from error
    from av import VideoFrame
    from av.codec.context import CodecContext
    from av.video.codeccontext import ColorRange
    from fractions import Fraction

    rgb = np.clip(hdr.rgba[..., :3] * 203.0 / 10000.0, 0, 1)
    # PQ 电光转换的逆操作，保持 BT.2020 色度。
    m1, m2 = 2610 / 16384, 2523 / 32
    c1, c2, c3 = 3424 / 4096, 2413 / 128, 2392 / 128
    p = rgb ** m1
    encoded = ((c1 + c2 * p) / (1 + c3 * p)) ** m2
    frame = VideoFrame.from_ndarray(np.rint(encoded * 65535).astype(np.uint16), format="rgb48le")
    frame = frame.reformat(format="yuv420p10le", dst_colorspace=9)
    for frame_or_context in (frame,):
        frame_or_context.color_primaries = 9
        frame_or_context.color_trc = 16
        frame_or_context.colorspace = 9
        frame_or_context.color_range = ColorRange.MPEG
    with av.open(str(path), "w", format="avif") as container:
        stream = container.add_stream("libsvtav1", rate=Fraction(1))
        stream.width = hdr.rgba.shape[1]
        stream.height = hdr.rgba.shape[0]
        stream.pix_fmt = "yuv420p10le"
        stream.options = {"crf": "18", "preset": "8"}
        stream.codec_context.color_primaries = 9
        stream.codec_context.color_trc = 16
        stream.codec_context.colorspace = 9
        stream.codec_context.color_range = ColorRange.MPEG
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
