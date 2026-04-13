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

    def test_collision_predicted_as_skip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        src = tmp_path / "backups" / "phone" / "IMG_001.jpg"
        dest_dir = tmp_path / "photos" / "2024" / "Q1"
        existing = dest_dir / "IMG_001.jpg"
        _write_file(src, b"source content")
        _write_file(existing, b"different existing content")  # Same name, different content

        result = dry_run_batch([MoveAssignment(str(src), str(dest_dir))])

        assert result.files[0].action == "skip_duplicate"
        assert result.files[0].final_filename == "IMG_001.jpg"

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
    async def test_collision_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        src = tmp_path / "backups" / "phone" / "IMG_030.jpg"
        dest_dir = tmp_path / "photos" / "2025" / "Q1"
        existing = dest_dir / "IMG_030.jpg"
        _write_file(src, b"source bytes")
        _write_file(existing, b"different existing bytes")

        result = await execute_batch([MoveAssignment(str(src), str(dest_dir))])

        assert result.files[0].action == "skip_duplicate"
        assert src.exists()  # Source kept when skipped
        assert not (dest_dir / "IMG_030_1.jpg").exists()  # No renamed copy created


# ---------------------------------------------------------------------------
# Log router — action filter
# ---------------------------------------------------------------------------

class TestLogRowsActionFilter:
    """Unit-tests for the action= query parameter on GET /api/move/log/rows."""

    def _make_entries(self) -> list[dict]:
        return [
            {"timestamp": "2026-01-01T10:00:00", "action": "move",           "src": "/a/x.jpg",   "dest": "/b/x.jpg",   "note": "", "error": ""},
            {"timestamp": "2026-01-01T10:00:01", "action": "skip_duplicate", "src": "/a/y.jpg",   "dest": "/b/y.jpg",   "note": "", "error": ""},
            {"timestamp": "2026-01-01T10:00:02", "action": "delete_error",   "src": "/a/z.jpg",   "dest": "",           "note": "", "error": "Permission denied"},
            {"timestamp": "2026-01-01T10:00:03", "action": "scan_complete",  "src": "",           "dest": "",           "note": "total_files=5", "error": ""},
        ]

    def test_no_filter_returns_all(self) -> None:
        from app.routers.move import _esc
        entries = self._make_entries()
        # Substring match "" matches everything
        filtered = [e for e in entries if "".lower() in e["action"].lower()]
        assert len(filtered) == 4

    def test_error_filter_matches_delete_error_and_scan_error(self) -> None:
        entries = self._make_entries()
        filtered = [e for e in entries if "error" in e["action"].lower()]
        assert len(filtered) == 1
        assert filtered[0]["action"] == "delete_error"

    def test_move_filter_matches_only_move(self) -> None:
        entries = self._make_entries()
        filtered = [e for e in entries if "move" in e["action"].lower()]
        assert len(filtered) == 1
        assert filtered[0]["action"] == "move"

    def test_scan_filter_matches_scan_events(self) -> None:
        entries = self._make_entries()
        filtered = [e for e in entries if "scan" in e["action"].lower()]
        assert len(filtered) == 1
        assert filtered[0]["action"] == "scan_complete"

    def test_esc_helper_sanitises_html_chars(self) -> None:
        from app.routers.move import _esc
        assert _esc('<script>&') == '&lt;script&gt;&amp;'
