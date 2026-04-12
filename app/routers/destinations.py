"""Destinations API router (FR-05–FR-08, FR-18)."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.destinations import (
    create_event_folder,
    ensure_child_folder,
    list_child_folders,
    list_event_categories,
    list_event_folders,
    resolve_quarterly_path,
)

router = APIRouter(prefix="/api/destinations", tags=["destinations"])

MediaTypeParam = Literal["photo", "video"]


# ---------------------------------------------------------------------------
# Event categories and folders
# ---------------------------------------------------------------------------


@router.get("/categories")
async def get_categories(media_type: MediaTypeParam) -> dict:
    """List top-level category folders under the library root."""
    return {"categories": list_event_categories(media_type)}


@router.get("/events")
async def get_events(media_type: MediaTypeParam, category: str) -> dict:
    """List event folders within a category."""
    return {"events": list_event_folders(media_type, category)}


class CreateEventRequest(BaseModel):
    media_type: MediaTypeParam
    category: str
    name: str


@router.post("/events")
async def create_event(req: CreateEventRequest) -> dict:
    """Create a new event folder (and any required intermediate directories)."""
    try:
        path = create_event_folder(req.media_type, req.category, req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(path), "created": True}


# ---------------------------------------------------------------------------
# HTML fragment endpoints (used by HTMX in the review UI)
# ---------------------------------------------------------------------------


@router.get("/category-options", response_class=HTMLResponse)
async def get_category_options(media_type: MediaTypeParam) -> str:
    """Return <option> elements for the category dropdown."""
    categories = list_event_categories(media_type)
    if not categories:
        return '<option value="">– no folders found –</option>'
    return "\n".join(f'<option value="{c}">{c}</option>' for c in categories)


@router.get("/event-options", response_class=HTMLResponse)
async def get_event_options(media_type: MediaTypeParam, category: str = "") -> str:
    """Return <option> elements for the event dropdown given a category."""
    if not category:
        return '<option value="">– select a category first –</option>'
    events = list_event_folders(media_type, category)
    if not events:
        return '<option value="">– no sub-folders found –</option>'
    return "\n".join(f'<option value="{e}">{e}</option>' for e in events)


@router.get("/all-event-zones")
async def get_all_event_zones() -> dict:
    """Return all event directories with their full native paths (used by the drag-and-drop UI)."""
    from pathlib import Path
    from app.config import get_config

    cfg = get_config()
    photos_root = Path(cfg.library.photos_root)
    videos_root = Path(cfg.library.videos_root)

    zones = []
    for cat in list_event_categories("photo"):
        zones.append({"dir": str(photos_root / cat), "label": f"📷 {cat}"})
    for cat in list_event_categories("video"):
        zones.append({"dir": str(videos_root / cat), "label": f"🎬 {cat}"})
    return {"zones": zones}


# ---------------------------------------------------------------------------
# Manual destination folder picker
# ---------------------------------------------------------------------------


@router.get("/child-folders")
async def get_child_folders(root: Literal["photos", "videos"]) -> dict:
    """List first-level subdirectories under the photos or videos library root."""
    media_type = "photo" if root == "photos" else "video"
    return {"folders": list_child_folders(media_type)}


class EnsureFolderRequest(BaseModel):
    root: Literal["photos", "videos"]
    name: str


@router.post("/ensure-folder")
async def ensure_folder(req: EnsureFolderRequest) -> dict:
    """Create ``<library_root>/<name>`` if it does not yet exist.

    The name must be a simple folder name (no path separators).
    """
    media_type = "photo" if req.root == "photos" else "video"
    try:
        path = ensure_child_folder(media_type, req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(path), "created": True}


# ---------------------------------------------------------------------------
# Quarterly paths
# ---------------------------------------------------------------------------


@router.get("/quarterly")
async def get_quarterly(
    media_type: MediaTypeParam,
    capture_date: str,  # ISO date string: YYYY-MM-DD
) -> dict:
    """Return the computed quarterly destination path for a given capture date."""
    try:
        d = date.fromisoformat(capture_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid date: {capture_date}") from exc

    path = resolve_quarterly_path(media_type, d)
    return {"path": str(path), "exists": path.exists()}
