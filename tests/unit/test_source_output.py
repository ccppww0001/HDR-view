from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from hdrview.errors import OutputConflictError, SourceChangedError
from hdrview.io.output import publish_outputs, validate_output_dir
from hdrview.io.source import assert_original_unchanged, read_source


def test_read_source_hashes_exact_bytes_without_modifying_file(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"\xff\xd8original\xff\xd9")
    original_stat = source.stat()

    document = read_source(source)

    assert document.path == source
    assert document.data == b"\xff\xd8original\xff\xd9"
    assert document.sha256 == hashlib.sha256(document.data).hexdigest()
    assert source.read_bytes() == document.data
    assert source.stat().st_mtime_ns == original_stat.st_mtime_ns


def test_read_source_rejects_directory_and_missing_file(tmp_path: Path):
    with pytest.raises((IsADirectoryError, FileNotFoundError)):
        read_source(tmp_path)
    with pytest.raises(FileNotFoundError):
        read_source(tmp_path / "missing.jpg")


def test_publish_outputs_writes_directly_into_existing_directory(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "first.jpg").write_bytes(b"first")
    (staging / "second.jpg").write_bytes(b"second")
    output_root = tmp_path / "results"
    output_root.mkdir()
    (output_root / "existing.jpg").write_bytes(b"existing")

    publish_outputs(staging, output_root, [source])

    assert {path.name: path.read_bytes() for path in output_root.iterdir()} == {
        "existing.jpg": b"existing", "first.jpg": b"first", "second.jpg": b"second",
    }


def test_publish_outputs_rejects_collision_before_writing_any_files(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "first.jpg").write_bytes(b"first")
    (staging / "second.jpg").write_bytes(b"second")
    output_root = tmp_path / "results"
    output_root.mkdir()
    (output_root / "second.jpg").write_bytes(b"existing")

    with pytest.raises(OutputConflictError, match="second.jpg"):
        publish_outputs(staging, output_root, [source])

    assert {path.name: path.read_bytes() for path in output_root.iterdir()} == {"second.jpg": b"existing"}


def test_output_cannot_be_source_or_its_parent(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")

    with pytest.raises(OutputConflictError):
        validate_output_dir(source, [source])
    with pytest.raises(OutputConflictError):
        validate_output_dir(tmp_path, [source])


def test_output_rejects_symlinked_root(tmp_path: Path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "source.jpg"
    source.write_bytes(b"source")
    real_output = tmp_path / "real-output"
    real_output.mkdir()
    linked_output = tmp_path / "linked-output"
    if os.name == "nt":
        import _winapi

        try:
            _winapi.CreateJunction(str(real_output), str(linked_output))
        except PermissionError:
            # 受限执行环境可能拒绝创建联接，此时不能实际验证联接路径。
            pytest.skip("当前 Windows 执行环境未授予目录联接创建权限")
    else:
        linked_output.symlink_to(real_output, target_is_directory=True)

    with pytest.raises(OutputConflictError):
        validate_output_dir(linked_output, [source])


def test_original_hash_change_is_detected(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"before")
    document = read_source(source)
    source.write_bytes(b"after")

    with pytest.raises(SourceChangedError):
        assert_original_unchanged(document)


def test_original_same_content_is_accepted(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"same")
    document = read_source(source)

    assert_original_unchanged(document)
