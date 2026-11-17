from __future__ import annotations

import struct
from pathlib import Path

import pytest

from hdrview.errors import InvalidJpegError
from hdrview.vivo.container import (
    inspect_jpeg,
    locate_vivo_trailer,
    scan_jpeg,
)


def segment(marker: int, payload: bytes) -> bytes:
    return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload


def synthetic_jpeg(*, entropy: bytes = b"image", trailer: bytes = b"") -> bytes:
    main = (
        b"\xff\xd8"
        + segment(0xE1, b"Exif\x00\x00metadata")
        + segment(0xDA, b"scan")
        + entropy
        + b"\xff\xd9"
    )
    return main + trailer


def vivo_trailer(auxiliary: bytes, *, json_text: bytes = b'{"com.vivo.xdr.maxGain":4.5}') -> bytes:
    """实测 Neo9 Pro 布局：streamdata 在主图后，streaminfo 在文件末尾。"""

    info = (
        b"streaminfo\x00\x03\x00\x01\x01\x00\x00\x00\x00\x00"
        + b"streamcount\x00\x01vivo"
        + json_text
        + b"\x00\x00\x00\x00camera"
    )
    return b"streamdata" + auxiliary + info


def test_scan_records_app_segments_and_the_real_eoi():
    data = synthetic_jpeg(entropy=b"abc\xff\x00\xd8\xff\xd0\xff\x00\xd8hidden\xff\x00\xd9")

    segments = scan_jpeg(data)

    assert [item.marker for item in segments] == [0xE1, 0xDA, 0xD9]
    assert segments[-1].offset == len(data) - 2
    assert segments[0].length == 18


def test_scan_accepts_jpeg_without_app_segments():
    data = b"\xff\xd8" + segment(0xDA, b"scan") + b"pixels\xff\xd9"

    segments = scan_jpeg(data)

    assert [item.marker for item in segments] == [0xDA, 0xD9]


def test_scan_rejects_non_jpeg_and_truncated_segment():
    with pytest.raises(InvalidJpegError):
        scan_jpeg(b"not a jpeg")
    with pytest.raises(InvalidJpegError):
        scan_jpeg(b"\xff\xd8\xff\xe1\x00\x20short")


def test_scan_rejects_segment_length_below_two():
    with pytest.raises(InvalidJpegError):
        scan_jpeg(b"\xff\xd8\xff\xe1\x00\x01")


def test_trailer_uses_declared_offsets_not_embedded_jpeg_signatures():
    auxiliary = b"\xff\xd8" + segment(0xDA, b"aux") + b"auxiliary\xff\xd9"
    data = synthetic_jpeg(
        entropy=b"main\xff\x00\xd8fake-thumbnail\xff\x00\xd9",
        trailer=vivo_trailer(auxiliary),
    )

    located = locate_vivo_trailer(data)

    assert located is not None
    assert located.data_offset == len(data) - len(vivo_trailer(auxiliary)) + len(b"streamdata")
    assert located.data_length == len(auxiliary)
    assert data[located.data_offset : located.data_offset + located.data_length] == auxiliary
    assert located.info_offset == len(data) - (len(vivo_trailer(auxiliary)) - len(auxiliary) - len(b"streamdata"))
    assert located.primary_eoi_offset < located.data_offset


def test_trailer_returns_none_for_plain_sdr_jpeg():
    assert locate_vivo_trailer(synthetic_jpeg()) is None


def test_trailer_accepts_single_nul_padding_with_original_offsets():
    auxiliary = synthetic_jpeg()
    primary = synthetic_jpeg()
    data = primary + b"\x00" + vivo_trailer(auxiliary)

    located = locate_vivo_trailer(data)

    assert located is not None
    assert located.primary_eoi_offset == len(primary) - 2
    assert located.data_offset == len(primary) + 1 + len(b"streamdata")
    assert data[located.data_offset : located.info_offset] == auxiliary
    assert located.data_length == len(auxiliary)


def test_trailer_does_not_accept_arbitrary_gap_before_streamdata():
    assert locate_vivo_trailer(synthetic_jpeg(trailer=b"\x00\x00" + vivo_trailer(synthetic_jpeg()))) is None


def test_trailer_rejects_invalid_auxiliary_jpeg():
    with pytest.raises(InvalidJpegError):
        locate_vivo_trailer(synthetic_jpeg(trailer=vivo_trailer(b"not-jpeg")))


def test_trailer_rejects_multiple_or_truncated_declarations():
    auxiliary = b"\xff\xd8\xff\xd9"
    with pytest.raises(InvalidJpegError):
        locate_vivo_trailer(synthetic_jpeg(trailer=vivo_trailer(auxiliary) + vivo_trailer(auxiliary)))
    with pytest.raises(InvalidJpegError):
        locate_vivo_trailer(synthetic_jpeg(trailer=b"streamdata\xff\xd8\xff\xd9streaminfo\x00short"))


def test_inspect_returns_document_with_hash_and_no_vivo_for_plain_jpeg(tmp_path: Path):
    source = tmp_path / "plain.jpg"
    data = synthetic_jpeg()
    source.write_bytes(data)

    document = inspect_jpeg(source)

    assert document.source_path == source
    assert document.sha256 is not None
    assert document.vivo is None
    assert document.jpeg_segments[-1].marker == 0xD9
