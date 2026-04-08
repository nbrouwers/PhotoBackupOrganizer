"""Backup folder scanner.

Scans all configured device backup folders, identifies unprocessed media
files, extracts capture dates, and returns a structured result grouped by
device and date (FR-01 – FR-04, NFR-03).

The scan is designed to be run as a FastAPI background task so the UI
remains responsive during long operations (NFR-04).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.config import get_config
from app.database import is_processed
from app.metadata import MediaType, get_capture_date, get_media_type

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MediaFile:
    """Metadata about a single discovered media file."""

    path: str  # Absolute path inside the container
    filename: str
    media_type: MediaType
    capture_date: date
    capture_datetime: datetime
    size_bytes: int
    device_label: str


@dataclass
class DateGroup:
    """All media files from one device captured on the same date."""

    date: date
    files: list[MediaFile] = field(default_factory=list)


@dataclass
class DeviceGroup:
    """All unprocessed media files from one backup device."""

    label: str
    date_groups: list[DateGroup] = field(default_factory=list)


@dataclass
class ScanResult:
    """Top-level result returned by :func:`scan_all_devices`."""

    devices: list[DeviceGroup] = field(default_factory=list)
    total_files: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scan progress (shared state for status polling)
# ---------------------------------------------------------------------------


class ScanProgress:
    def __init__(self) -> None:
        self.running: bool = False
        self.current_device: Optional[str] = None
        self.scanned: int = 0
        self.found: int = 0
        self.result: Optional[ScanResult] = None
        self.error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "current_device": self.current_device,
            "scanned": self.scanned,
            "found": self.found,
            "done": not self.running and self.result is not None,
            "error": self.error,
        }


_progress = ScanProgress()


def get_scan_progress() -> ScanProgress:
    return _progress


def get_last_scan_result() -> Optional[ScanResult]:
    return _progress.result


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------


async def _scan_device(device_path: Path, device_label: str) -> tuple[list[MediaFile], list[str]]:
    """Recursively scan a single device folder and return (files, errors)."""
    cfg = get_config()
    files: list[MediaFile] = []
    errors: list[str] = []

    if not device_path.exists():
        errors.append(f"Device path does not exist: {device_path}")
        return files, errors

    candidates = [
        p for p in device_path.rglob("*")
        if p.is_file() and p.suffix.lower() in cfg.all_extensions
    ]

    for file_path in candidates:
        path_str = str(file_path)
        try:
            if await is_processed(path_str):
                continue

            media_type = get_media_type(file_path)
            if media_type is None:
                continue

            capture_dt = await get_capture_date(file_path)
            size = file_path.stat().st_size

            files.append(
                MediaFile(
                    path=path_str,
                    filename=file_path.name,
                    media_type=media_type,
                    capture_date=capture_dt.date(),
                    capture_datetime=capture_dt,
                    size_bytes=size,
                    device_label=device_label,
                )
            )
        except Exception as exc:
            logger.warning("Error processing %s: %s", file_path, exc)
            errors.append(f"{path_str}: {exc}")

    return files, errors


def _group_by_date(files: list[MediaFile]) -> list[DateGroup]:
    """Group a flat list of MediaFile objects by capture date."""
    groups: dict[date, DateGroup] = {}
    for f in sorted(files, key=lambda x: x.capture_datetime):
        if f.capture_date not in groups:
            groups[f.capture_date] = DateGroup(date=f.capture_date)
        groups[f.capture_date].files.append(f)
    return list(groups.values())


async def scan_all_devices() -> ScanResult:
    """Scan all configured devices and return a structured :class:`ScanResult`.

    Updates the module-level :class:`ScanProgress` so callers can poll
    ``/api/scan/status`` while the scan runs.
    """
    global _progress
    _progress = ScanProgress()
    _progress.running = True
    cfg = get_config()
    result = ScanResult()

    try:
        for device_cfg in cfg.devices:
            _progress.current_device = device_cfg.label
            device_path = Path(device_cfg.path)

            files, errors = await _scan_device(device_path, device_cfg.label)
            result.errors.extend(errors)
            _progress.scanned += sum(1 for _ in Path(device_cfg.path).rglob("*") if Path(_).is_file()) if device_path.exists() else 0
            _progress.found += len(files)

            if files:
                date_groups = _group_by_date(files)
                result.devices.append(
                    DeviceGroup(label=device_cfg.label, date_groups=date_groups)
                )
                result.total_files += len(files)

            # Yield control so other async tasks can run
            await asyncio.sleep(0)

    except Exception as exc:
        _progress.error = str(exc)
        logger.exception("Scan failed: %s", exc)
    finally:
        _progress.running = False
        _progress.result = result

    return result
