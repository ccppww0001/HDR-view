from __future__ import annotations

import importlib
from types import SimpleNamespace

import numpy as np
import pytest

from hdrview.color.transfer import pq_to_linear_bt2020
from hdrview.model import SdrImage
from hdrview.nvidia.runtime import TrueHdrParams, run_truehdr, truehdr_to_hdr, unpack_pq_rgb10a2


def test_default_parameters_and_validation():
    params = TrueHdrParams()

    assert (params.contrast, params.saturation, params.middle_gray, params.luminance, params.debanding) == (100, 100, 50, 1000, True)
    params.validate()
    for invalid in (
        TrueHdrParams(contrast=-1),
        TrueHdrParams(contrast=201),
        TrueHdrParams(saturation=-1),
        TrueHdrParams(saturation=201),
        TrueHdrParams(middle_gray=9),
        TrueHdrParams(middle_gray=101),
        TrueHdrParams(luminance=399),
        TrueHdrParams(luminance=2001),
        TrueHdrParams(debanding=1),
    ):
        with pytest.raises(ValueError):
            invalid.validate()


@pytest.mark.parametrize(
    "params",
    [
        TrueHdrParams(contrast=0, saturation=0, middle_gray=10, luminance=400),
        TrueHdrParams(contrast=200, saturation=200, middle_gray=100, luminance=2000),
    ],
)
def test_truehdr_parameters_accept_inclusive_endpoints(params):
    params.validate()


def test_unpack_pq_rgb10a2_extracts_unsigned_channels_without_torch():
    packed = np.array([[0, 1023 | (512 << 10) | (1 << 20), 0xFFFFFFFF]], dtype=np.uint32)

    result = unpack_pq_rgb10a2(packed)

    assert result.dtype == np.float32
    assert result.shape == (1, 3, 3)
    np.testing.assert_array_equal(result[0, 0], [0, 0, 0])
    np.testing.assert_allclose(result[0, 1], [1, 512 / 1023, 1 / 1023])
    np.testing.assert_array_equal(result[0, 2], [1, 1, 1])


@pytest.mark.parametrize(
    "packed",
    [
        np.zeros((1, 1, 1), dtype=np.uint32),
        np.zeros((0, 1), dtype=np.uint32),
        np.zeros((1, 1), dtype=np.float32),
        np.array([[-1]], dtype=np.int64),
    ],
)
def test_unpack_pq_rgb10a2_rejects_invalid_input(packed):
    with pytest.raises(ValueError):
        unpack_pq_rgb10a2(packed)


def test_truehdr_to_hdr_decodes_absolute_pq_and_records_actual_capacity():
    # 合成 PQ 仅验证共享色彩转换，不代表执行了真实 NVIDIA 模型。
    pq = np.zeros((1, 2, 3), dtype=np.float32)
    pq[0, 1] = 1.0
    params = TrueHdrParams(luminance=1000)

    result = truehdr_to_hdr(pq, source_sha256="a" * 64, params=params)

    expected = pq_to_linear_bt2020(pq) / 203
    np.testing.assert_allclose(result.rgba[..., :3], expected, rtol=1e-6)
    np.testing.assert_array_equal(result.rgba[..., 3], 1)
    assert result.color.primaries == "bt2020"
    assert result.color.transfer == "linear"
    assert result.hdr_capacity_max == pytest.approx(float(np.max(expected)))
    assert result.provenance == {
        "pipeline": "nvidia-truehdr",
        "source_sha256": "a" * 64,
        "contrast": 100,
        "saturation": 100,
        "middle_gray": 50,
        "luminance": 1000,
        "debanding": True,
    }


def test_truehdr_to_hdr_capacity_has_sdr_floor_and_rejects_invalid_pq():
    result = truehdr_to_hdr(np.zeros((1, 1, 3), dtype=np.float32), source_sha256="b" * 64, params=TrueHdrParams())
    assert result.hdr_capacity_max == 1.0

    with pytest.raises(ValueError):
        truehdr_to_hdr(np.full((1, 1, 3), np.nan), source_sha256="b" * 64, params=TrueHdrParams())
    with pytest.raises(ValueError):
        truehdr_to_hdr(np.full((1, 1, 3), 1.1), source_sha256="b" * 64, params=TrueHdrParams())
    with pytest.raises(ValueError):
        truehdr_to_hdr(np.zeros((1, 1), dtype=np.float32), source_sha256="b" * 64, params=TrueHdrParams())
    with pytest.raises(ValueError, match="SHA-256"):
        truehdr_to_hdr(np.zeros((1, 1, 3), dtype=np.float32), source_sha256="bad", params=TrueHdrParams())
    with pytest.raises(ValueError, match="PQ"):
        truehdr_to_hdr(np.full((1, 1, 3), 0.5 + 0.25j, dtype=np.complex64), source_sha256="b" * 64, params=TrueHdrParams())


class _FakeCuda:
    def __init__(self):
        self.available = True
        self.device_names = ["NVIDIA Test Device"]
        self.entered_devices = []
        self.created_streams = 0

    def is_available(self):
        return self.available

    def get_device_name(self, index):
        return self.device_names[index]

    def device(self, index):
        entered = self.entered_devices
        return _Context(entered, index)

    def Stream(self, device):
        self.created_streams += 1
        return SimpleNamespace(cuda_stream=2468, device=device)

    def stream(self, stream):
        raise AssertionError("TrueHDR 必须使用官方默认流，不能切换私有流")


class _Context:
    def __init__(self, log, value):
        self.log = log
        self.value = value

    def __enter__(self):
        self.log.append(self.value)
        return self.value

    def __exit__(self, *args):
        return False


class _FakeTensor:
    def __init__(self, array, log, torch_module=None):
        self.array = np.asarray(array)
        self.log = log
        self.torch_module = torch_module

    def permute(self, *axes):
        return _FakeTensor(np.transpose(self.array, axes), self.log, self.torch_module)

    def contiguous(self):
        return _FakeTensor(np.ascontiguousarray(self.array), self.log, self.torch_module)

    def to(self, device, dtype):
        self.log.append(("to", device, dtype, self.array.shape))
        return self

    @property
    def shape(self):
        return self.array.shape

    @property
    def dtype(self):
        return self.array.dtype

    def clone(self):
        return _FakeTensor(self.array.copy(), self.log, self.torch_module)

    def cpu(self):
        self.log.append(("cpu",))
        return self

    def numpy(self):
        return self.array

    def __rshift__(self, bits):
        return _FakeTensor(self.array.astype(np.uint32) >> bits, self.log, self.torch_module)

    def __and__(self, mask):
        return _FakeTensor(self.array.astype(np.uint32) & mask, self.log, self.torch_module)

    def float(self):
        return _FakeTensor(self.array.astype(np.float32), self.log, self.torch_module)

    def __truediv__(self, divisor):
        return _FakeTensor(self.array / divisor, self.log, self.torch_module)


class _FakeTorch:
    def __init__(self, packed):
        self.cuda = _FakeCuda()
        self.log = []
        self.packed = packed
        self.float32 = np.float32
        self.uint32 = np.uint32

    def from_numpy(self, array):
        self.log.append(("from_numpy", array.copy()))
        return _FakeTensor(array, self.log, self)

    def from_dlpack(self, image):
        self.log.append(("from_dlpack", image))
        return _FakeTensor(self.packed, self.log, self)

    def stack(self, tensors, dim):
        self.log.append(("stack", dim))
        return _FakeTensor(np.stack([tensor.array for tensor in tensors], axis=dim), self.log, self)


class _FakeTrueHdr:
    def __init__(self, log, packed, **kwargs):
        self.log = log
        self.packed = packed
        self.kwargs = kwargs

    def __enter__(self):
        self.log.append("enter")
        return self

    def load(self):
        self.log.append("load")

    def run(self, image, *, stream_ptr):
        self.log.append(("run", image, stream_ptr))
        return SimpleNamespace(image=SimpleNamespace(dlpack=self.packed))

    def __exit__(self, *args):
        self.log.append("close")
        return False


class _FakeNvvfx:
    __version__ = "0.2.0.0"

    def __init__(self, packed):
        self.packed = packed
        self.log = []

    def TrueHDR(self, **kwargs):
        self.log.append(("construct", kwargs))
        return _FakeTrueHdr(self.log, self.packed, **kwargs)


def _sdr():
    rgba = np.array([[[13, 26, 51, 255]]], dtype=np.uint8)
    return SdrImage(rgba, None, None)


def test_run_truehdr_invalid_params_and_hash_fail_before_import(monkeypatch):
    def unexpected_import(name):
        raise AssertionError(f"参数校验前不应导入运行时：{name}")

    monkeypatch.setattr(importlib, "import_module", unexpected_import)
    with pytest.raises(ValueError):
        run_truehdr(_sdr(), TrueHdrParams(luminance=399), "d" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        run_truehdr(_sdr(), TrueHdrParams(), "invalid")


def test_run_truehdr_uses_direct_api_and_closes_model(monkeypatch):
    # 这里只模拟官方接口；不声称已验证 PyTorch 的真实 DLPack 互操作或 GPU 推理。
    packed = np.array([[1023 | (1023 << 10) | (1023 << 20)]], dtype=np.uint32)
    fake_torch = _FakeTorch(packed)
    fake_nvvfx = _FakeNvvfx(packed)
    real_import = importlib.import_module

    def fake_import(name):
        if name == "torch":
            return fake_torch
        if name == "nvvfx":
            return fake_nvvfx
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    result = run_truehdr(_sdr(), TrueHdrParams(contrast=110, saturation=90, middle_gray=55, luminance=1200, debanding=False), "c" * 64)

    assert fake_nvvfx.log[0] == ("construct", {"contrast": 110, "saturation": 90, "middle_gray": 55, "luminance": 1200, "debanding_off": 1, "device": 0})
    assert fake_nvvfx.log[1:] == ["enter", "load", ("run", fake_nvvfx.log[3][1], 0), "close"]
    run_tensor = fake_nvvfx.log[3][1]
    np.testing.assert_allclose(run_tensor.array[:, 0, 0], [((13 / 255 + 0.055) / 1.055) ** (2.4 / 2.2), ((26 / 255 + 0.055) / 1.055) ** (2.4 / 2.2), ((51 / 255 + 0.055) / 1.055) ** (2.4 / 2.2)], rtol=1e-6)
    assert fake_torch.cuda.entered_devices == [0]
    assert fake_torch.cuda.created_streams == 0
    assert ("to", "cuda:0", np.dtype(np.float32), (3, 1, 1)) in fake_torch.log
    dlpack_call = next(call for call in fake_torch.log if call[0] == "from_dlpack")
    np.testing.assert_array_equal(dlpack_call[1].dlpack, packed)
    assert result.provenance["nvidia-vfx"] == "0.2.0.0"
    assert result.provenance["source_sha256"] == "c" * 64
    assert result.provenance["content_hdr_capacity_max"] == result.hdr_capacity_max
    np.testing.assert_allclose(result.rgba[0, 0, :3], pq_to_linear_bt2020(np.ones(3, dtype=np.float32)) / 203, rtol=1e-6)


@pytest.mark.parametrize(
    ("packed", "message"),
    [
        (np.zeros((2, 1), dtype=np.uint32), "尺寸"),
        (np.zeros((1, 1), dtype=np.int32), "uint32"),
    ],
)
def test_run_truehdr_rejects_invalid_native_output_and_closes_model(monkeypatch, packed, message):
    fake_torch = _FakeTorch(packed)
    fake_nvvfx = _FakeNvvfx(packed)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_torch if name == "torch" else fake_nvvfx)

    with pytest.raises((RuntimeError, ValueError), match=message):
        run_truehdr(_sdr(), TrueHdrParams(), "d" * 64)

    assert fake_nvvfx.log[-1] == "close"


def test_run_truehdr_version_metadata_fallback_and_mismatch(monkeypatch):
    packed = np.zeros((1, 1), dtype=np.uint32)
    fake_torch = _FakeTorch(packed)
    fake_nvvfx = _FakeNvvfx(packed)
    fake_nvvfx.__version__ = None
    fake_nvvfx.VERSION = 200
    from hdrview.nvidia import runtime
    monkeypatch.setattr(runtime, "_import_runtime", lambda: (fake_torch, fake_nvvfx))
    monkeypatch.setattr("importlib.metadata.version", lambda name: "0.2.0.0" if name == "nvidia-vfx" else None)

    result = run_truehdr(_sdr(), TrueHdrParams(), "d" * 64)

    assert result.provenance["nvidia-vfx"] == "0.2.0.0"
    assert result.provenance["content_hdr_capacity_max"] == result.hdr_capacity_max

    fake_nvvfx.__version__ = "0.2.1"
    with pytest.raises(RuntimeError, match=r"nvidia-vfx.*0\.2\.0\.0"):
        run_truehdr(_sdr(), TrueHdrParams(), "d" * 64)
    assert fake_nvvfx.log[-1] == "close"


def test_run_truehdr_unavailable_cuda_does_not_construct_model(monkeypatch):
    packed = np.zeros((1, 1), dtype=np.uint32)
    fake_torch = _FakeTorch(packed)
    fake_torch.cuda.available = False
    fake_nvvfx = _FakeNvvfx(packed)
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_torch if name == "torch" else fake_nvvfx)

    with pytest.raises(RuntimeError, match="CUDA"):
        run_truehdr(_sdr(), TrueHdrParams(), "d" * 64)

    assert fake_nvvfx.log == []


@pytest.mark.parametrize("method", ["load", "run"])
def test_run_truehdr_model_errors_close_and_preserve_cause(monkeypatch, method):
    packed = np.zeros((1, 1), dtype=np.uint32)
    fake_torch = _FakeTorch(packed)
    fake_nvvfx = _FakeNvvfx(packed)
    error = OSError(f"{method} failed")
    model = fake_nvvfx.TrueHDR()
    setattr(model, method, lambda *args, **kwargs: (_ for _ in ()).throw(error))
    fake_nvvfx.TrueHDR = lambda **kwargs: model
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_torch if name == "torch" else fake_nvvfx)

    with pytest.raises(RuntimeError, match="TrueHDR") as caught:
        run_truehdr(_sdr(), TrueHdrParams(), "d" * 64)

    assert caught.value.__cause__ is error
    assert fake_nvvfx.log[-1] == "close"


def test_run_truehdr_missing_dependencies_and_non_nvidia_cuda_fail_explicitly(monkeypatch):
    real_import = importlib.import_module

    def missing_import(name):
        if name in {"torch", "nvvfx"}:
            raise ImportError(name)
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", missing_import)
    with pytest.raises(RuntimeError, match=r"nvidia-vfx==0\.2\.0\.0.*PyTorch 2\.11\.0\+cu128.*\.venv-nvidia"):
        run_truehdr(_sdr(), TrueHdrParams(), "d" * 64)

    fake_torch = _FakeTorch(np.zeros((1, 1), dtype=np.uint32))
    fake_torch.cuda.device_names = ["Other GPU"]
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_torch if name == "torch" else _FakeNvvfx(np.zeros((1, 1), dtype=np.uint32)))
    with pytest.raises(RuntimeError, match="NVIDIA"):
        run_truehdr(_sdr(), TrueHdrParams(), "d" * 64)
