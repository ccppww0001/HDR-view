"""真实原图的只读兼容性集成测试；私有样本不复制到仓库。"""

from pathlib import Path

import pytest

from hdrview.vivo.auxiliary import classify_support, extract_auxiliary_jpeg
from hdrview.vivo.container import inspect_jpeg

SAMPLES = Path(__file__).resolve().parents[2] / "images/fromthephone"


@pytest.mark.parametrize("filename", [
    "IMG_20261111_175548.jpg", "IMG_20261111_175601.jpg", "IMG_20261116_204341.jpg",
    "IMG_20261116_212648.jpg", "IMG_20261116_212653.jpg",
])
def test_known_phone_sample_has_read_only_auxiliary_jpeg(filename):
    path = SAMPLES / filename
    if not path.is_file():
        pytest.skip("私人原始样本不在工作区")
    original = path.read_bytes()
    document = inspect_jpeg(path)
    assert classify_support(document).supported
    assert extract_auxiliary_jpeg(document).startswith(b"\xff\xd8")
    assert path.read_bytes() == original
