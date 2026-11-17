"""真实原图的只读兼容性集成测试；私有样本不复制到仓库。"""

from pathlib import Path

import pytest

from hdrview.vivo.auxiliary import classify_support, extract_auxiliary_jpeg
from hdrview.vivo.container import inspect_jpeg

SAMPLES = Path(r"D:\MyProject\HDR-view\images\fromthephone")


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="私人原始样本不在工作区")
def test_all_phone_samples_have_read_only_auxiliary_jpegs():
    hashes_before = {}
    for path in sorted(SAMPLES.glob("*.jpg")):
        hashes_before[path.name] = path.read_bytes()
        document = inspect_jpeg(path)
        assert classify_support(document).supported
        assert extract_auxiliary_jpeg(document).startswith(b"\xff\xd8")
    # 保留最初四张基线，同时自动覆盖后续加入的同机型原图。
    assert {"IMG_20261111_175548.jpg", "IMG_20261111_175601.jpg",
            "IMG_20261116_212648.jpg", "IMG_20261116_212653.jpg"} <= hashes_before.keys()
    for name, original in hashes_before.items():
        assert (SAMPLES / name).read_bytes() == original
