from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from hdrview.errors import InvalidIntermediateError
from hdrview.io.intermediate import intermediate_paths, read_intermediate, write_intermediate
from hdrview.model import ColorState, HdrImage


def hdr_image(values: np.ndarray | None = None) -> HdrImage:
    rgba = np.zeros((2, 3, 4), dtype=np.float32) if values is None else values
    rgba[..., 3] = 1.0
    return HdrImage(
        rgba=rgba,
        color=ColorState(primaries="bt2020", transfer="linear"),
        hdr_capacity_max=4.0,
        provenance={"source_sha256": "a" * 64, "pipeline": "test"},
    )


def test_float16_intermediate_roundtrip_and_metadata(tmp_path: Path):
    image = hdr_image()
    image.rgba[1, 2, :3] = [4.0, 2.0, 1.0]

    paths = write_intermediate(image, tmp_path / "image")
    restored = read_intermediate(paths.stem)

    assert paths.pixel.exists()
    assert paths.metadata.exists()
    assert restored.rgba.dtype == np.float32
    assert restored.rgba.shape == (2, 3, 4)
    np.testing.assert_allclose(restored.rgba, image.rgba, atol=0.002)
    assert restored.color.primaries == "bt2020"
    assert restored.color.sdr_white_nits == 203.0
    assert restored.hdr_capacity_max == 4.0
    assert restored.provenance["source_sha256"] == "a" * 64


def test_missing_sidecar_is_rejected(tmp_path: Path):
    (tmp_path / "image.f16rgba").write_bytes(b"\0" * 48)
    with pytest.raises(InvalidIntermediateError):
        read_intermediate(tmp_path / "image")


@pytest.mark.parametrize(
    "change",
    [
        lambda image: image.rgba.__setitem__((0, 0, 0), np.nan),
        lambda image: image.rgba.__setitem__((0, 0, 0), -0.1),
        lambda image: image.rgba.__setitem__((0, 0, 0), 65505.0),
    ],
)
def test_invalid_pixel_values_are_not_clamped_or_saved(tmp_path: Path, change):
    image = hdr_image()
    change(image)
    with pytest.raises(InvalidIntermediateError):
        write_intermediate(image, tmp_path / "bad")


def test_invalid_color_and_capacity_are_rejected(tmp_path: Path):
    for image in [
        HdrImage(np.zeros((1, 1, 4), dtype=np.float32), ColorState("rec709", "linear"), 2.0, {"source_sha256": "a" * 64}),
        HdrImage(np.zeros((1, 1, 4), dtype=np.float32), ColorState("bt2020", "linear"), 0.5, {"source_sha256": "a" * 64}),
    ]:
        with pytest.raises(InvalidIntermediateError):
            write_intermediate(image, tmp_path / "bad")


def test_read_rejects_wrong_pixel_byte_length(tmp_path: Path):
    image = hdr_image()
    paths = write_intermediate(image, tmp_path / "image")
    paths.pixel.write_bytes(b"short")

    with pytest.raises(InvalidIntermediateError):
        read_intermediate(paths.stem)


def test_dotted_photo_names_remain_distinct_and_explicit_paths_are_readable(tmp_path: Path):
    first = write_intermediate(hdr_image(), tmp_path / "photo.one-truehdr")
    second = write_intermediate(hdr_image(), tmp_path / "photo.two-truehdr")
    assert first.pixel.name == "photo.one-truehdr.f16rgba"
    assert second.pixel.name == "photo.two-truehdr.f16rgba"
    assert first.pixel != second.pixel
    for path in (first.stem, first.pixel, first.metadata):
        assert intermediate_paths(path) == first
        np.testing.assert_array_equal(read_intermediate(path).rgba, hdr_image().rgba)
