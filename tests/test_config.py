"""Tests for app/config.py."""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from app.config import reload_config


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "config.yaml"


def write_config(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def test_valid_config_loads(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_config(
        config_path,
        """
        devices:
          - label: "Test Phone"
            path: /backups/test
        library:
          photos_root: /photos
          videos_root: /videos
        """,
    )
    monkeypatch.setenv("PHOTO_BACKUP_CONFIG", str(config_path))
    cfg = reload_config()

    assert len(cfg.devices) == 1
    assert cfg.devices[0].label == "Test Phone"
    assert cfg.library.photos_root == "/photos"
    assert cfg.library.videos_root == "/videos"


def test_default_extensions_present(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_config(
        config_path,
        """
        devices:
          - label: "Phone"
            path: /backups/phone
        library:
          photos_root: /photos
          videos_root: /videos
        """,
    )
    monkeypatch.setenv("PHOTO_BACKUP_CONFIG", str(config_path))
    cfg = reload_config()

    assert ".jpg" in cfg.all_photo_extensions
    assert ".mp4" in cfg.all_video_extensions


def test_missing_config_file_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHOTO_BACKUP_CONFIG", "/nonexistent/config.yaml")
    with pytest.raises(SystemExit):
        reload_config()


def test_missing_library_raises(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_config(
        config_path,
        """
        devices:
          - label: "Phone"
            path: /backups/phone
        """,
    )
    monkeypatch.setenv("PHOTO_BACKUP_CONFIG", str(config_path))
    with pytest.raises(SystemExit):
        reload_config()


def test_relative_device_path_raises(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_config(
        config_path,
        """
        devices:
          - label: "Phone"
            path: relative/path
        library:
          photos_root: /photos
          videos_root: /videos
        """,
    )
    monkeypatch.setenv("PHOTO_BACKUP_CONFIG", str(config_path))
    with pytest.raises(SystemExit):
        reload_config()


def test_multiple_devices(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_config(
        config_path,
        """
        devices:
          - label: Alice
            path: /backups/alice
          - label: Bob
            path: /backups/bob
        library:
          photos_root: /photos
          videos_root: /videos
        """,
    )
    monkeypatch.setenv("PHOTO_BACKUP_CONFIG", str(config_path))
    cfg = reload_config()
    labels = [d.label for d in cfg.devices]
    assert labels == ["Alice", "Bob"]
