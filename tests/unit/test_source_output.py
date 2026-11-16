from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from hdrview.errors import OutputConflictError, SourceChangedError
from hdrview.io.output import create_output_dir
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


def test_create_output_dir_makes_a_new_child_run_directory(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    output_root = tmp_path / "results"

    run_dir = create_output_dir(output_root, sources=[source])

    assert run_dir.parent == output_root
    assert run_dir.is_dir()
    assert list(run_dir.iterdir()) == []


def test_create_output_dir_never_reuses_existing_run(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    output_root = tmp_path / "results"

    first = create_output_dir(output_root, sources=[source])
    second = create_output_dir(output_root, sources=[source])

    assert first != second
    assert first.name == "run-001"
    assert second.name == "run-002"


def test_output_cannot_be_source_or_its_parent(tmp_path: Path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")

    with pytest.raises(OutputConflictError):
        create_output_dir(source, sources=[source])
    with pytest.raises(OutputConflictError):
        create_output_dir(tmp_path, sources=[source])


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

        _winapi.CreateJunction(str(real_output), str(linked_output))
    else:
        linked_output.symlink_to(real_output, target_is_directory=True)

    with pytest.raises(OutputConflictError):
        create_output_dir(linked_output, sources=[source])


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
