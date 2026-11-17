from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from hdrview.model import SdrImage
from hdrview.nvidia.comfy_workflow import TrueHdrParams, build_workflow
from hdrview.nvidia.preprocess import prepare_truehdr_input


def test_truehdr_input_is_rec709_gamma22_not_srgb_passthrough():
    rgba = np.zeros((1, 2, 4), dtype=np.uint8)
    rgba[0, 0, :3] = [13, 13, 13]
    rgba[..., 3] = 255
    sdr = SdrImage(rgba, None, None)

    result = prepare_truehdr_input(sdr)

    assert result.dtype == np.float32
    assert result.shape == (1, 2, 3)
    assert result[0, 0, 0] == pytest.approx(((13 / 255 + 0.055) / 1.055) ** (2.4 / 2.2), rel=1e-6)
    assert not np.array_equal(result, rgba[..., :3].astype(np.float32) / 255)


def test_truehdr_input_rejects_alpha_or_wrong_shape():
    with pytest.raises(ValueError):
        prepare_truehdr_input(SdrImage(np.zeros((2, 2, 3), dtype=np.uint8), None, None))


def test_workflow_connects_custom_preprocess_official_rtx_and_linear_save():
    workflow = build_workflow(Path("input.png"), TrueHdrParams())
    nodes = {node["type"]: node for node in workflow["nodes"]}

    assert "HdrViewPrepareTrueHDR" in nodes
    assert "RTXTrueHDR" in nodes
    assert "HdrViewSaveLinear" in nodes
    assert nodes["RTXTrueHDR"]["widgets_values"]["output_colorspace"] == "HDR PQ"
    assert nodes["RTXTrueHDR"]["widgets_values"]["debanding"] is True
    assert nodes["RTXTrueHDR"]["widgets_values"]["luminance"] == 400
    assert "SaveImage" not in nodes
    links = workflow["links"]
    assert any(link[1] == nodes["HdrViewPrepareTrueHDR"]["id"] and link[3] == nodes["RTXTrueHDR"]["id"] for link in links)
    assert any(link[1] == nodes["RTXTrueHDR"]["id"] and link[3] == nodes["HdrViewSaveLinear"]["id"] for link in links)


def test_workflow_rejects_hlg_and_invalid_parameters():
    with pytest.raises(ValueError):
        build_workflow(Path("input.png"), TrueHdrParams(output_colorspace="HDR"))
    with pytest.raises(ValueError):
        TrueHdrParams(luminance=399).validate()
