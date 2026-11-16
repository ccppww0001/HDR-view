"""严格读取 streaminfo 中的 vivo JSON，不推导私有高光公式。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math

from hdrview.errors import InvalidVivoDataError


@dataclass(frozen=True)
class VivoMetadata:
    max_gain: float | None
    json: dict


def parse_vivo_metadata(data: bytes) -> VivoMetadata:
    """JSON 固定跟随 streamcount/vivo，到首个 NUL 结束。"""

    marker = b"streamcount\x00\x01vivo"
    position = data.find(marker)
    if position < 0:
        raise InvalidVivoDataError("streaminfo 缺少 streamcount/vivo JSON")
    start = position + len(marker)
    end = data.find(b"\x00", start)
    if end < 0:
        raise InvalidVivoDataError("vivo JSON 未正确结束")
    try:
        value = json.loads(data[start:end].decode("utf-8"), parse_constant=lambda text: (_ for _ in ()).throw(ValueError(text)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise InvalidVivoDataError("vivo JSON 损坏或含非有限值") from error
    if not isinstance(value, dict):
        raise InvalidVivoDataError("vivo JSON 顶层不是对象")
    max_gain = value.get("com.vivo.xdr.maxGain")
    if not isinstance(max_gain, (int, float)) or isinstance(max_gain, bool):
        raise InvalidVivoDataError("缺少数值型 com.vivo.xdr.maxGain")
    if not math.isfinite(max_gain) or not 1 <= max_gain <= 1000:
        raise InvalidVivoDataError("vivo maxGain 超出安全研究范围 [1,1000]")
    return VivoMetadata(max_gain=float(max_gain), json=value)
