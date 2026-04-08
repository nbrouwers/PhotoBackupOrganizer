"""Tests for app/destinations.py."""
from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import pytest


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
    from app.config import reload_config
    reload_config()


class TestResolveQuarterlyPath:
    @pytest.mark.parametrize(
        "month, expected_quarter",
        [(1, "Q1"), (2, "Q1"), (3, "Q1"),
         (4, "Q2"), (5, "Q2"), (6, "Q2"),
         (7, "Q3"), (8, "Q3"), (9, "Q3"),
         (10, "Q4"), (11, "Q4"), (12, "Q4")],
    )
    def test_quarter_assignment(
        self, month: int, expected_quarter: str,
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_config(tmp_path, monkeypatch)
        from app.destinations import resolve_quarterly_path

        d = date(2025, month, 15)
        path = resolve_quarterly_path("photo", d)
        assert path.name == expected_quarter
        assert str(path).startswith(str(tmp_path / "photos" / "2025"))

    def test_photo_uses_photos_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        from app.destinations import resolve_quarterly_path

        path = resolve_quarterly_path("photo", date(2025, 3, 1))
        assert str(path).startswith(str(tmp_path / "photos"))

    def test_video_uses_videos_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _setup_config(tmp_path, monkeypatch)
        from app.destinations import resolve_quarterly_path

        path = resolve_quarterly_path("video", date(2025, 3, 1))
        assert str(path).startswith(str(tmp_path / "videos"))


class TestEventFolders:
    def test_list_categories_empty_when_no_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_config(tmp_path, monkeypatch)
        (tmp_path / "photos").mkdir(parents=True, exist_ok=True)
        from app.destinations import list_event_categories

        categories = list_event_categories("photo")
        assert categories == []

    def test_list_categories_excludes_year_folders(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_config(tmp_path, monkeypatch)
        photos = tmp_path / "photos"
        (photos / "2025").mkdir(parents=True)
        (photos / "holidays").mkdir(parents=True)
        (photos / "birthdays").mkdir(parents=True)

        from app.destinations import list_event_categories

        categories = list_event_categories("photo")
        assert "holidays" in categories
        assert "birthdays" in categories
        assert "2025" not in categories

    def test_create_event_folder_creates_dirs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_config(tmp_path, monkeypatch)
        from app.destinations import create_event_folder

        path = create_event_folder("photo", "holidays", "2025 Amsterdam")
        assert path.exists()
        assert path.is_dir()
        assert path.name == "2025 Amsterdam"
        assert path.parent.name == "holidays"

    def test_path_traversal_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_config(tmp_path, monkeypatch)
        from app.destinations import create_event_folder

        with pytest.raises(ValueError, match="outside the library root"):
            create_event_folder("photo", "../evil", "escape")

    def test_list_event_folders(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setup_config(tmp_path, monkeypatch)
        photos = tmp_path / "photos"
        (photos / "holidays" / "2025 Amsterdam").mkdir(parents=True)
        (photos / "holidays" / "2024 Paris").mkdir(parents=True)

        from app.destinations import list_event_folders

        events = list_event_folders("photo", "holidays")
        assert "2025 Amsterdam" in events
        assert "2024 Paris" in events
