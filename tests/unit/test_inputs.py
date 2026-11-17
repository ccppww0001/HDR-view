"""目录命令正确识别 JPEG 扩展名，并跳过同名目录。"""

from hdrview.io.inputs import jpeg_inputs


def test_jpeg_directory_includes_extensions_and_case(tmp_path):
    expected = [tmp_path / name for name in ("a.jpg", "b.jpeg", "c.JPG", "d.JPEG")]
    for path in expected:
        path.write_bytes(b"fixture")
    (tmp_path / "skip.png").write_bytes(b"fixture")
    (tmp_path / "directory.jpg").mkdir()
    assert jpeg_inputs(tmp_path) == expected
    assert jpeg_inputs(expected[1]) == [expected[1]]
