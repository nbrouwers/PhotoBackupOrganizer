"""Scan API router (FR-01–FR-04)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks

from app.scanner import get_last_scan_result, get_scan_progress, scan_all_devices

router = APIRouter(prefix="/api/scan", tags=["scan"])

_scan_lock = asyncio.Lock()


@router.get("/status")
async def scan_status() -> dict:
    """Poll the current scan progress."""
    return get_scan_progress().to_dict()


@router.post("")
async def trigger_scan(background_tasks: BackgroundTasks) -> dict:
    """Trigger a background device scan (FR-01).

    Returns immediately; poll ``GET /api/scan/status`` for progress.
    If a scan is already running, returns its current status.
    """
    progress = get_scan_progress()
    if progress.running:
        return {"status": "already_running", **progress.to_dict()}

    background_tasks.add_task(scan_all_devices)
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
