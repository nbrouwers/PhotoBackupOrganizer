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
from app.metadata import MediaType, get_capture_date, get_gps_coords, get_media_type

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
    gps: Optional[tuple[float, float]] = None  # (lat, lon) in decimal degrees


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
        self.current_file: Optional[str] = None   # filename being processed right now
        self.scanned: int = 0                      # files processed so far (across all devices)
        self.total: int = 0                        # total media files discovered in pre-count
        self.found: int = 0                        # unprocessed files found so far
        self.cancelled: bool = False               # set to True to request cancellation
        self.result: Optional[ScanResult] = None
        self.error: Optional[str] = None
        # Accumulates as each device finishes: [{label, found}]
        self.device_counts: list[dict[str, object]] = []

    def request_cancel(self) -> None:
        """Signal the running scan to stop after the current file."""
        if self.running:
            self.cancelled = True

    @property
    def percent(self) -> int:
        """0-100 progress percentage; 0 while total is not yet known."""
        if not self.total:
            return 0
        return min(100, round(self.scanned * 100 / self.total))

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "current_device": self.current_device,
            "current_file": self.current_file,
            "scanned": self.scanned,
            "total": self.total,
            "found": self.found,
            "percent": self.percent,
            "cancelled": self.cancelled,
            "done": not self.running and self.result is not None,
            "error": self.error,
            "device_counts": self.device_counts,
        }


_progress = ScanProgress()


def get_scan_progress() -> ScanProgress:
    return _progress


def get_last_scan_result() -> Optional[ScanResult]:
    return _progress.result


# ---------------------------------------------------------------------------
# Core scan logic
# ---------------------------------------------------------------------------


def _collect_candidates(
    device_path: Path,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[Path]:
    """Return media files under *device_path* (recursive, sorted).

    Synology NAS creates ``@eaDir`` directories alongside every folder it
    manages.  These contain internal thumbnail / metadata files (e.g.
    ``SYNOPHOTO:0_THUMB.jpg``) that look like ordinary JPEG files.  They are
    excluded here so that Synology-generated artefacts never appear in the
    review UI.

    When *date_from* or *date_to* are given, files whose modification date
    falls outside the range are excluded (fast mtime pre-filter).
    """
    cfg = get_config()
    results = []
    for p in device_path.rglob("*"):
        # Skip Synology internal directories and their contents
        if "@eaDir" in p.parts:
            continue
        # Skip Synology thumbnail / metadata files by name prefix
        if p.name.startswith("SYNOPHOTO"):
            continue
        if not (p.is_file() and p.suffix.lower() in cfg.all_extensions):
            continue
        if date_from is not None or date_to is not None:
            mtime = date.fromtimestamp(p.stat().st_mtime)
            if date_from is not None and mtime < date_from:
                continue
            if date_to is not None and mtime > date_to:
                continue
        results.append(p)
    return sorted(results)


async def _scan_device(
    device_path: Path,
    device_label: str,
    candidates: list[Path],
) -> tuple[list[MediaFile], list[str]]:
    """Process *candidates* for one device and return (files, errors).

    Updates the module-level ``_progress`` as each file is examined.
    """
    files: list[MediaFile] = []
    errors: list[str] = []

    logger.info(
        "[%s] Starting scan of %s — %d candidate file(s)",
        device_label, device_path, len(candidates),
    )

    for idx, file_path in enumerate(candidates, start=1):
        # Check cancellation between every file
        if _progress.cancelled:
            logger.info("[%s] Scan cancelled after %d/%d files", device_label, idx - 1, len(candidates))
            break

        path_str = str(file_path)
        _progress.current_file = file_path.name

        logger.debug(
            "[%s] Examining file %d/%d: %s",
            device_label, idx, len(candidates), file_path.name,
        )

        try:
            if await is_processed(path_str):
                logger.debug("[%s] Skipping already-processed file: %s", device_label, file_path.name)
                _progress.scanned += 1
                await asyncio.sleep(0)
                continue

            media_type = get_media_type(file_path)
            if media_type is None:
                _progress.scanned += 1
                await asyncio.sleep(0)
                continue

            capture_dt = await get_capture_date(file_path)
            size = file_path.stat().st_size
            gps = get_gps_coords(file_path) if media_type == "photo" else None

            logger.debug(
                "[%s] Found %s: %s  capture=%s  size=%d bytes%s",
                device_label, media_type, file_path.name,
                capture_dt.date().isoformat(), size,
                f"  gps={gps}" if gps else "",
            )

            files.append(
                MediaFile(
                    path=path_str,
                    filename=file_path.name,
                    media_type=media_type,
                    capture_date=capture_dt.date(),
                    capture_datetime=capture_dt,
                    size_bytes=size,
                    device_label=device_label,
                    gps=gps,
                )
            )
            _progress.found += 1

        except Exception as exc:
            logger.warning("[%s] Error processing %s: %s", device_label, file_path, exc)
            errors.append(f"{path_str}: {exc}")

        _progress.scanned += 1
        # Yield every 10 files so the event loop can handle status polls
        if idx % 10 == 0:
            await asyncio.sleep(0)

    logger.info(
        "[%s] Scan complete — examined %d, unprocessed found %d, errors %d",
        device_label, len(candidates), len(files), len(errors),
    )
    return files, errors


def _group_by_date(files: list[MediaFile]) -> list[DateGroup]:
    """Group a flat list of MediaFile objects by capture date."""
    groups: dict[date, DateGroup] = {}
    for f in sorted(files, key=lambda x: x.capture_datetime):
        if f.capture_date not in groups:
            groups[f.capture_date] = DateGroup(date=f.capture_date)
        groups[f.capture_date].files.append(f)
    return list(groups.values())


async def scan_all_devices(
    include_paths: Optional[list[str]] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> ScanResult:
    """Scan configured devices and return a structured :class:`ScanResult`.

    Parameters
    ----------
    include_paths:
        When provided, only the listed sub-folders (absolute paths that fall
        inside a configured device root) are walked.  ``None`` scans all.
    date_from / date_to:
        Optional mtime-based pre-filter; files outside the window are skipped
        before any metadata is read (fast quarter-based scope reduction).

    Updates the module-level :class:`ScanProgress` so callers can poll
    ``/api/scan/status`` for live progress.
    """
    global _progress
    _progress = ScanProgress()
    _progress.running = True
    cfg = get_config()
    result = ScanResult()

    try:
        # ── Phase 1: pre-count all candidate files ────────────────────────
        logger.info(
            "Scan started — %d device(s), include_paths=%s, date_from=%s, date_to=%s",
            len(cfg.devices), include_paths, date_from, date_to,
        )
        device_candidates: list[tuple[str, Path, list[Path]]] = []

        for device_cfg in cfg.devices:
            device_path = Path(device_cfg.path)
            _progress.current_device = device_cfg.label
            _progress.current_file = None

            # Determine which sub-roots to walk for this device
            if include_paths is not None:
                scan_roots = [
                    Path(p) for p in include_paths
                    if Path(p).is_relative_to(device_path)
                ]
                if not scan_roots:
                    device_candidates.append((device_cfg.label, device_path, []))
                    continue
            else:
                scan_roots = None

            if not device_path.exists():
                logger.warning("[%s] Device path does not exist: %s", device_cfg.label, device_path)
                result.errors.append(f"Device path does not exist: {device_path}")
                device_candidates.append((device_cfg.label, device_path, []))
                continue

            logger.info("[%s] Pre-counting files in %s …", device_cfg.label, device_path)
            roots = scan_roots if scan_roots else [device_path]
            candidates: list[Path] = []
            for root in roots:
                if root.exists():
                    candidates.extend(_collect_candidates(root, date_from, date_to))
            candidates = sorted(set(candidates))

            device_candidates.append((device_cfg.label, device_path, candidates))
            _progress.total += len(candidates)
            logger.info("[%s] Found %d media file(s) to examine", device_cfg.label, len(candidates))
            await asyncio.sleep(0)

        logger.info("Pre-count complete — %d total media file(s) across all devices", _progress.total)

        # ── Phase 2: process each device ──────────────────────────────────
        for device_label, device_path, candidates in device_candidates:
            if _progress.cancelled:
                logger.info("Scan cancelled — skipping remaining devices")
                break

            _progress.current_device = device_label
            _progress.current_file = None

            if not candidates:
                _progress.device_counts.append({"label": device_label, "found": 0})
                continue

            files, errors = await _scan_device(device_path, device_label, candidates)
            result.errors.extend(errors)

            device_found = len(files)
            _progress.device_counts.append({"label": device_label, "found": device_found})

            if files:
                date_groups = _group_by_date(files)
                result.devices.append(DeviceGroup(label=device_label, date_groups=date_groups))
                result.total_files += len(files)

            await asyncio.sleep(0)

    except Exception as exc:
        logger.exception("Unexpected error during scan: %s", exc)
        _progress.error = str(exc)
        logger.exception("Scan failed: %s", exc)
    finally:
        _progress.running = False
        _progress.result = result

    return result
