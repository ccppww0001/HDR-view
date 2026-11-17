"""视频超分辨率模式、原生生命周期及派生基础图契约。"""

from types import SimpleNamespace

import numpy as np
import pytest

from hdrview.model import SdrImage
from hdrview.nvidia import runtime
from hdrview.nvidia.vsr import VsrParams, _encode_sdr, run_vsr


@pytest.mark.parametrize(("mode", "size", "quality"), [
    ("upscale", (8, 6), "HIGH"), ("denoise", (4, 3), "DENOISE_HIGH"),
    ("deblur", (4, 3), "DEBLUR_HIGH"),
])
def test_vsr_modes_map_to_official_models(mode, size, quality):
    params = VsrParams(mode=mode)
    assert params.output_size(4, 3) == size
    assert params.quality_name == quality


@pytest.mark.parametrize("params", [
    VsrParams(mode="unknown"), VsrParams(quality="unknown"), VsrParams(scale=True),
    VsrParams(scale=1), VsrParams(strength=float("nan")), VsrParams(strength=-0.1),
    VsrParams(strength=1.1), VsrParams(strength=True),
])
def test_vsr_invalid_options_fail_before_loading(params, monkeypatch):
    monkeypatch.setattr(runtime, "_import_runtime", lambda: pytest.fail("无效参数不应加载模型"))
    with pytest.raises(ValueError):
        run_vsr(SdrImage(np.full((3, 4, 4), 128, dtype=np.uint8), None, None), params, "a" * 64)


def test_vsr_output_budget_is_checked_before_native_allocation():
    with pytest.raises(ValueError, match="预算"):
        VsrParams().output_size(10000, 10000)


def test_vsr_sdr_roundtrip_preserves_neutral_and_uses_srgb_profile():
    result = _encode_sdr(np.full((16, 16, 3), 0.5, dtype=np.float32))
    assert result.rgba.dtype == np.uint8
    assert result.rgba.shape == (16, 16, 4)
    # gamma 2.2 的 0.5 还原线性后再编码 sRGB，约 129/255。
    np.testing.assert_allclose(result.rgba[..., :3], 129, atol=2)
    np.testing.assert_array_equal(result.rgba[..., 3], 255)
    assert result.compressed_jpeg.startswith(b"\xff\xd8")
    assert result.icc is not None


class Tensor:
    def __init__(self, data):
        self.data = data

    def permute(self, *axes):
        return Tensor(self.data.transpose(axes))

    def contiguous(self):
        return self

    def to(self, **kwargs):
        return self

    def clone(self):
        return Tensor(self.data.copy())

    def cpu(self):
        return self

    def numpy(self):
        return self.data

    @property
    def dtype(self):
        return self.data.dtype

    @property
    def shape(self):
        return self.data.shape


def install_runtime(monkeypatch, output, fail=None):
    from contextlib import nullcontext
    events = []

    class Model:
        def __init__(self, **kwargs):
            events.append(("construct", kwargs))

        def __enter__(self):
            return self

        def load(self):
            events.append(("load", self.output_width, self.output_height))
            if fail == "load":
                raise OSError("load failed")

        def run(self, tensor, *, stream_ptr):
            events.append(("run", tensor.shape, stream_ptr))
            if fail == "run":
                raise OSError("run failed")
            return SimpleNamespace(image=output)

        def __exit__(self, *args):
            events.append("close")

    torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True, get_device_name=lambda index: "NVIDIA Test", device=lambda index: nullcontext()),
        float32=np.float32, from_numpy=Tensor, from_dlpack=Tensor,
    )
    nvvfx = SimpleNamespace(__version__="0.2.0.0", QualityLevel=SimpleNamespace(DENOISE_HIGH=10), VideoSuperRes=Model)
    monkeypatch.setattr(runtime, "_import_runtime", lambda: (torch, nvvfx))
    return events


def test_vsr_native_execution_configures_dimensions_and_closes_model(monkeypatch):
    events = install_runtime(monkeypatch, np.full((3, 4, 6), 0.5, dtype=np.float32))
    result = run_vsr(SdrImage(np.full((4, 6, 4), 128, dtype=np.uint8), None, None), VsrParams(mode="denoise"), "a" * 64)
    assert events == [("construct", {"quality": 10, "strength": 1.0, "device": 0}), ("load", 6, 4), ("run", (3, 4, 6), 0), "close"]
    assert result.report["executed"] is True
    assert result.report["scale"] == 1
    assert result.report["source_sha256"] == "a" * 64
    assert result.image.rgba.shape == (4, 6, 4)


@pytest.mark.parametrize("output", [np.zeros((3, 4, 5), np.float32), np.zeros((3, 4, 6), np.float64), np.full((3, 4, 6), np.nan, np.float32)])
def test_vsr_rejects_invalid_output_and_closes_native_model(monkeypatch, output):
    events = install_runtime(monkeypatch, output)
    with pytest.raises(RuntimeError):
        run_vsr(SdrImage(np.full((4, 6, 4), 128, dtype=np.uint8), None, None), VsrParams(mode="denoise"), "a" * 64)
    assert events[-1] == "close"


@pytest.mark.parametrize("stage", ["load", "run"])
def test_vsr_native_failure_closes_model_and_preserves_cause(monkeypatch, stage):
    events = install_runtime(monkeypatch, np.zeros((3, 4, 6), np.float32), fail=stage)
    with pytest.raises(RuntimeError) as error:
        run_vsr(SdrImage(np.full((4, 6, 4), 128, dtype=np.uint8), None, None), VsrParams(mode="denoise"), "a" * 64)
    assert isinstance(error.value.__cause__, OSError)
    assert events[-1] == "close"
