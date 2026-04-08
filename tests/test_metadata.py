"""Tests for app/metadata.py."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

# Patch config before importing metadata
import textwrap


def _write_minimal_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            devices:
              - label: "Test"
                path: /backups/test
            library:
              photos_root: /photos
              videos_root: /videos
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PHOTO_BACKUP_CONFIG", str(cfg))
    from app.config import reload_config
    reload_config()


def _make_jpeg(path: Path, exif_date: str | None = None) -> None:
    """Create a minimal JPEG, optionally with an EXIF DateTimeOriginal."""
    img = Image.new("RGB", (10, 10), color=(100, 150, 200))
    if exif_date:
        import piexif
        exif_dict = {
            "Exif": {piexif.ExifIFD.DateTimeOriginal: exif_date.encode()}
        }
        exif_bytes = piexif.dump(exif_dict)
        img.save(str(path), "JPEG", exif=exif_bytes)
    else:
        img.save(str(path), "JPEG")


class TestGetMediaType:
    def test_jpeg_is_photo(self, tmp_path, monkeypatch):
        _write_minimal_config(tmp_path, monkeypatch)
        from app.metadata import get_media_type
        assert get_media_type(tmp_path / "IMG_001.jpg") == "photo"

    def test_heic_is_photo(self, tmp_path, monkeypatch):
        _write_minimal_config(tmp_path, monkeypatch)
        from app.metadata import get_media_type
        assert get_media_type(tmp_path / "IMG_001.HEIC") == "photo"

    def test_mp4_is_video(self, tmp_path, monkeypatch):
        _write_minimal_config(tmp_path, monkeypatch)
        from app.metadata import get_media_type
        assert get_media_type(tmp_path / "VID_001.mp4") == "video"

    def test_mov_is_video(self, tmp_path, monkeypatch):
        _write_minimal_config(tmp_path, monkeypatch)
        from app.metadata import get_media_type
        assert get_media_type(tmp_path / "VID_001.MOV") == "video"

    def test_txt_is_none(self, tmp_path, monkeypatch):
        _write_minimal_config(tmp_path, monkeypatch)
        from app.metadata import get_media_type
        assert get_media_type(tmp_path / "notes.txt") is None


class TestGetCaptureDate:
    @pytest.mark.asyncio
    async def test_exif_date_extracted(self, tmp_path, monkeypatch):
        _write_minimal_config(tmp_path, monkeypatch)
        # Only run if piexif is available
        pytest.importorskip("piexif")
        from app.metadata import get_capture_date

        jpeg = tmp_path / "test.jpg"
        _make_jpeg(jpeg, exif_date="2024:06:15 10:30:00")

        dt = await get_capture_date(str(jpeg))
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.day == 15

    @pytest.mark.asyncio
    async def test_fallback_to_mtime(self, tmp_path, monkeypatch):
        _write_minimal_config(tmp_path, monkeypatch)
        from app.metadata import get_capture_date

        # Plain JPEG without EXIF
        jpeg = tmp_path / "no_exif.jpg"
        img = Image.new("RGB", (5, 5))
        img.save(str(jpeg), "JPEG")

        dt = await get_capture_date(str(jpeg))
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None
