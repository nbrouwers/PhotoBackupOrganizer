"""Scan API router (FR-01–FR-04)."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.config import get_config
from app.mover import write_log_entry
from app.scanner import get_available_quarters, get_last_scan_result, get_scan_progress, scan_all_devices

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


@router.post("/cancel")
async def cancel_scan() -> dict:
    """Request cancellation of the currently-running scan.

    Sets a flag that the scanner checks between files.  Returns immediately;
    the scan may process one more file before it actually stops.
    """
    progress = get_scan_progress()
    if not progress.running:
        return {"status": "not_running"}
    progress.request_cancel()
    return {"status": "cancelling"}


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

    background_tasks.add_task(_run_scan, include_paths, date_from, date_to)
    return {"status": "started"}


async def _run_scan(
    include_paths: Optional[list[str]],
    date_from: Optional[date],
    date_to: Optional[date],
) -> None:
    """Wrapper that logs scan start/end to the audit log before delegating."""
    scope = ", ".join(include_paths) if include_paths else "all devices"
    filters = ""
    if date_from or date_to:
        filters = f"date_from={date_from or '*'} date_to={date_to or '*'}"
    write_log_entry("scan_start", note=f"scope={scope}" + (f" {filters}" if filters else ""))
    try:
        await scan_all_devices(include_paths, date_from, date_to)
        result = get_last_scan_result()
        total = result.total_files if result else 0
        errors = result.errors if result else []
        if errors:
            for err in errors:
                write_log_entry("scan_error", note=str(err))
        write_log_entry("scan_complete", note=f"total_files={total} errors={len(errors)}")
    except Exception as exc:  # noqa: BLE001
        write_log_entry("scan_error", error=str(exc))


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


@router.get("/available-quarters")
async def available_quarters() -> dict:
    """Return list of quarters that have media files in backup locations (FR-01c†).

    Scans backup folders to find quarters with content, enabling smart filtering
    of quarter preset buttons on the scan page. Returns quarters sorted newest first.
    """
    quarters = get_available_quarters()
    return {"quarters": quarters}
