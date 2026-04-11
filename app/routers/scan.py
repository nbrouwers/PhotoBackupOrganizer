"""Scan API router (FR-01–FR-04)."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.config import get_config
from app.scanner import get_last_scan_result, get_scan_progress, scan_all_devices

router = APIRouter(prefix="/api/scan", tags=["scan"])

_scan_lock = asyncio.Lock()


class ScanRequest(BaseModel):
    """Optional JSON body for ``POST /api/scan``."""

    include_paths: Optional[list[str]] = None  # None → scan all devices
    date_from: Optional[str] = None  # ISO date "YYYY-MM-DD" — mtime lower bound
    date_to: Optional[str] = None    # ISO date "YYYY-MM-DD" — mtime upper bound


@router.get("/status")
async def scan_status() -> dict:
    """Poll the current scan progress."""
    return get_scan_progress().to_dict()


@router.post("")
async def trigger_scan(
    background_tasks: BackgroundTasks,
    body: Optional[ScanRequest] = None,
) -> dict:
    """Trigger a background device scan (FR-01).

    Returns immediately; poll ``GET /api/scan/status`` for progress.
    If a scan is already running, returns its current status.
    """
    progress = get_scan_progress()
    if progress.running:
        return {"status": "already_running", **progress.to_dict()}

    include_paths = body.include_paths if body else None
    date_from = date.fromisoformat(body.date_from) if body and body.date_from else None
    date_to   = date.fromisoformat(body.date_to)   if body and body.date_to   else None

    background_tasks.add_task(scan_all_devices, include_paths, date_from, date_to)
    return {"status": "started"}


@router.get("/result")
async def scan_result() -> dict:
    """Return the last completed scan result as a JSON-serialisable dict."""
    result = get_last_scan_result()
    if result is None:
        return {"devices": [], "total_files": 0, "errors": []}

    return {
        "total_files": result.total_files,
        "errors": result.errors,
        "devices": [
            {
                "label": dev.label,
                "date_groups": [
                    {
                        "date": dg.date.isoformat(),
                        "files": [
                            {
                                "path": f.path,
                                "filename": f.filename,
                                "media_type": f.media_type,
                                "capture_date": f.capture_date.isoformat(),
                                "capture_datetime": f.capture_datetime.isoformat(),
                                "size_bytes": f.size_bytes,
                            }
                            for f in dg.files
                        ],
                    }
                    for dg in dev.date_groups
                ],
            }
            for dev in result.devices
        ],
    }


@router.get("/folders")
async def list_scan_folders() -> dict:
    """List scannable sub-folders for each configured device (for UI preselection)."""
    cfg = get_config()
    devices = []
    for d in cfg.devices:
        device_path = Path(d.path)
        if not device_path.exists():
            devices.append({"label": d.label, "root": d.path, "subfolders": []})
            continue
        subdirs = sorted(p for p in device_path.iterdir() if p.is_dir())
        if subdirs:
            subfolders = [{"path": str(p), "name": p.name} for p in subdirs]
        else:
            subfolders = [{"path": d.path, "name": "(root — flat folder)"}]
        devices.append({"label": d.label, "root": d.path, "subfolders": subfolders})
    return {"devices": devices}
