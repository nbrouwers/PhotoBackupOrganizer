"""Tests for app/mover.py."""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from app.mover import MoveAssignment, dry_run_batch, execute_batch


def _setup_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            devices:
              - label: "Test"
                path: {tmp_path}/backups
            library:
              photos_root: {tmp_path}/photos
              videos_root: {tmp_path}/videos
            cache:
              path: {tmp_path}/cache
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PHOTO_BACKUP_CONFIG", str(cfg))
    monkeypatch.setenv("PHOTO_BACKUP_LOG_DIR", str(tmp_path / "logs"))
    from app.config import reload_config
    reload_config()


def _write_file(path: Path, content: bytes = b"test content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestDryRunBatch:
    def test_simple_move_predicted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        src = tmp_path / "backups" / "phone" / "IMG_001.jpg"
        dest_dir = tmp_path / "photos" / "2024" / "Q1"
        _write_file(src)

        result = dry_run_batch([MoveAssignment(str(src), str(dest_dir))])

        assert len(result.files) == 1
        assert result.files[0].action == "move"
        assert result.files[0].final_filename == "IMG_001.jpg"

    def test_collision_predicted_as_rename(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        src = tmp_path / "backups" / "phone" / "IMG_001.jpg"
        dest_dir = tmp_path / "photos" / "2024" / "Q1"
        existing = dest_dir / "IMG_001.jpg"
        _write_file(src, b"source content")
        _write_file(existing, b"different existing content")  # Not a duplicate

        result = dry_run_batch([MoveAssignment(str(src), str(dest_dir))])

        assert result.files[0].action == "rename"
        assert result.files[0].final_filename == "IMG_001_1.jpg"

    def test_duplicate_predicted_as_skip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        data = b"identical content bytes"
        src = tmp_path / "backups" / "phone" / "IMG_001.jpg"
        dest_dir = tmp_path / "photos" / "2024" / "Q1"
        existing = dest_dir / "IMG_001.jpg"
        _write_file(src, data)
        _write_file(existing, data)

        result = dry_run_batch([MoveAssignment(str(src), str(dest_dir))])

        assert result.files[0].action == "skip_duplicate"

    def test_dry_run_does_not_move_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        src = tmp_path / "backups" / "phone" / "IMG_002.jpg"
        dest_dir = tmp_path / "photos" / "2024" / "Q2"
        _write_file(src)

        dry_run_batch([MoveAssignment(str(src), str(dest_dir))])

        # Source must still exist; destination must NOT exist
        assert src.exists()
        assert not (dest_dir / "IMG_002.jpg").exists()


class TestExecuteBatch:
    @pytest.mark.asyncio
    async def test_file_moved_to_destination(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        src = tmp_path / "backups" / "phone" / "IMG_010.jpg"
        dest_dir = tmp_path / "photos" / "2024" / "Q3"
        _write_file(src, b"photo data")

        result = await execute_batch([MoveAssignment(str(src), str(dest_dir))])

        assert result.files[0].action == "move"
        assert (dest_dir / "IMG_010.jpg").exists()
        assert not src.exists()  # Source removed after successful copy (NFR-02)

    @pytest.mark.asyncio
    async def test_source_not_deleted_if_dest_write_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When dest_dir is a file (not a directory), copy will fail; source must survive."""
        _setup_config(tmp_path, monkeypatch)
        src = tmp_path / "backups" / "phone" / "IMG_011.jpg"
        # Make dest_dir point at an existing *file* so shutil.copy2 will fail
        bad_dest = tmp_path / "not_a_dir"
        bad_dest.write_bytes(b"I am a file")
        _write_file(src, b"photo data")

        result = await execute_batch([MoveAssignment(str(src), str(bad_dest))])

        assert result.files[0].action == "error"
        assert src.exists()  # Source must NOT have been deleted

    @pytest.mark.asyncio
    async def test_duplicate_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        data = b"duplicate bytes"
        src = tmp_path / "backups" / "phone" / "IMG_020.jpg"
        dest_dir = tmp_path / "photos" / "2024" / "Q4"
        existing = dest_dir / "IMG_020.jpg"
        _write_file(src, data)
        _write_file(existing, data)

        result = await execute_batch([MoveAssignment(str(src), str(dest_dir))])

        assert result.files[0].action == "skip_duplicate"
        assert src.exists()  # Not removed when skipped

    @pytest.mark.asyncio
    async def test_collision_resolved_with_suffix(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        src = tmp_path / "backups" / "phone" / "IMG_030.jpg"
        dest_dir = tmp_path / "photos" / "2025" / "Q1"
        existing = dest_dir / "IMG_030.jpg"
        _write_file(src, b"source bytes")
        _write_file(existing, b"different existing bytes")

        result = await execute_batch([MoveAssignment(str(src), str(dest_dir))])

        assert result.files[0].action == "rename"
        assert (dest_dir / "IMG_030_1.jpg").exists()
        assert not src.exists()
