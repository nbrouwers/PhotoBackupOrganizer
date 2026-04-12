"""UI HTML page router – serves Jinja2 templates for each workflow step."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_config
from app.scanner import get_last_scan_result, get_scan_progress

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")

# Add urlencode filter so templates can safely embed file paths in URLs
templates.env.filters["urlencode"] = lambda s, safe="": quote_plus(str(s), safe=safe)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Landing page – scan trigger and status."""
    progress = get_scan_progress()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"progress": progress.to_dict()},
    )


@router.get("/review", response_class=HTMLResponse)
async def review(request: Request) -> HTMLResponse:
    """Review unprocessed files grouped by device and date."""
    result = get_last_scan_result()
    devices = []
    if result:
        for dev in result.devices:
            device_data = {
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
                                "size_bytes": f.size_bytes,
                                "gps": list(f.gps) if f.gps else None,
                            }
                            for f in dg.files
                        ],
                    }
                    for dg in dev.date_groups
                ],
            }
            devices.append(device_data)

    cfg = get_config()
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "devices": devices,
            "scan_json": json.dumps(devices),
            "photos_root": str(cfg.library.photos_root),
            "videos_root": str(cfg.library.videos_root),
        },
    )


@router.get("/media")
async def serve_media(src: str) -> FileResponse:
    """Serve a raw media file for lightbox preview.

    Security: only paths that resolve to under a configured device backup root
    are permitted, preventing path traversal to arbitrary filesystem locations.
    """
    cfg          = get_config()
    allowed_roots = [Path(d.path).resolve() for d in cfg.devices]
    file_path     = Path(src).resolve()

    if not any(file_path.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied: path outside device roots")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(file_path))


@router.get("/scan/progress", response_class=HTMLResponse)
async def scan_progress_partial(request: Request) -> HTMLResponse:
    """HTMX partial — returns only the #scan-status inner HTML."""
    progress = get_scan_progress()
    return templates.TemplateResponse(
        request,
        "_scan_status.html",
        {"progress": progress.to_dict()},
    )


@router.get("/api/geocode")
async def geocode_location(lat: float, lon: float) -> dict:
    """Reverse-geocode *(lat, lon)* to a human-readable location string.

    Results are cached in SQLite; the first lookup for each location calls
    Nominatim (OpenStreetMap) at most once per second.
    """
    from app.geocoder import reverse_geocode
    location = await reverse_geocode(lat, lon)
    return {"location": location or ""}


@router.get("/confirm", response_class=HTMLResponse)
async def confirm(request: Request) -> HTMLResponse:
    """Dry-run preview confirmation page."""
    return templates.TemplateResponse(request, "confirm.html", {"files": []})


@router.get("/log", response_class=HTMLResponse)
async def log_view(request: Request) -> HTMLResponse:
    """Batch result and audit log viewer."""
    return templates.TemplateResponse(request, "log.html", {"entries": [], "summary": {}})
