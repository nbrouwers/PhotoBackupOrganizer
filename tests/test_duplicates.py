"""Tests for app/duplicates.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.duplicates import file_hash, is_duplicate


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestFileHash:
    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        data = b"hello world"
        a.write_bytes(data)
        b.write_bytes(data)
        assert file_hash(a) == file_hash(b)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        a.write_bytes(b"content A")
        b.write_bytes(b"content B")
        assert file_hash(a) != file_hash(b)

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.dat"
        f.write_bytes(b"")
        h = file_hash(f)
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex


class TestIsDuplicate:
    def test_identical_file_is_duplicate(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "photo.jpg"
        dest_dir = tmp_path / "dest"
        existing = dest_dir / "photo.jpg"
        data = b"identical content"
        _write(src, data)
        _write(existing, data)

        assert is_duplicate(src, dest_dir) is True

    def test_different_content_not_duplicate(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "photo.jpg"
        dest_dir = tmp_path / "dest"
        existing = dest_dir / "other.jpg"
        _write(src, b"source content")
        _write(existing, b"different content")

        assert is_duplicate(src, dest_dir) is False

    def test_nonexistent_dest_dir_not_duplicate(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "photo.jpg"
        _write(src, b"content")
        assert is_duplicate(src, tmp_path / "nonexistent") is False

    def test_same_size_different_content_not_duplicate(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "photo.jpg"
        dest_dir = tmp_path / "dest"
        existing = dest_dir / "other.jpg"
        # Same length, different content
        _write(src, b"AAAA")
        _write(existing, b"BBBB")

        assert is_duplicate(src, dest_dir) is False

    def test_empty_dest_dir_not_duplicate(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "photo.jpg"
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir(parents=True)
        _write(src, b"content")

        assert is_duplicate(src, dest_dir) is False
