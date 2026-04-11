"""Media file metadata extraction.

Provides:
- :func:`get_media_type` – classify a file as ``"photo"`` or ``"video"``.
- :func:`get_capture_date` – extract the capture date/time from EXIF (photos)
  or container metadata via ``ffprobe`` (videos), with fallback to the file's
  last-modified timestamp (FR-10).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import exifread

from app.config import get_config

logger = logging.getLogger(__name__)

MediaType = Literal["photo", "video"]

# EXIF tag names tried in priority order
_EXIF_DATE_TAGS = [
    "EXIF DateTimeOriginal",
    "EXIF DateTimeDigitized",
    "Image DateTime",
]
_EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"


def get_media_type(path: str | Path) -> Optional[MediaType]:
    """Return ``"photo"`` or ``"video"`` based on file extension, or ``None``
    if the extension is not recognised by the current configuration."""
    ext = Path(path).suffix.lower()
    cfg = get_config()
    if ext in cfg.all_photo_extensions:
        return "photo"
    if ext in cfg.all_video_extensions:
        return "video"
    return None


def _parse_exif_date(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value.strip(), _EXIF_DATE_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _extract_exif_date(path: Path) -> Optional[datetime]:
    try:
        with path.open("rb") as fh:
            tags = exifread.process_file(fh, stop_tag="EXIF DateTimeOriginal", details=False)
        for tag_name in _EXIF_DATE_TAGS:
            if tag_name in tags:
                date = _parse_exif_date(str(tags[tag_name]))
                if date:
                    return date
    except Exception as exc:
        logger.debug("EXIF extraction failed for %s: %s", path, exc)
    return None


async def _extract_ffprobe_date(path: Path) -> Optional[datetime]:
    """Run ``ffprobe`` to extract the ``creation_time`` from a video file."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format_tags=creation_time",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        data = json.loads(stdout)
        creation_time = (
            data.get("format", {}).get("tags", {}).get("creation_time")
        )
        if creation_time:
            # ISO 8601 e.g. "2024-08-15T14:30:00.000000Z"
            return datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
    except Exception as exc:
        logger.debug("ffprobe failed for %s: %s", path, exc)
    return None


def _mtime_date(path: Path) -> datetime:
    """Return the file's last-modified time as a UTC datetime."""
    mtime = os.path.getmtime(str(path))
    return datetime.fromtimestamp(mtime, tz=timezone.utc)


async def get_capture_date(path: str | Path) -> datetime:
    """Return the best available capture date for *path*.

    Priority:
    1. EXIF ``DateTimeOriginal`` / ``DateTimeDigitized`` / ``DateTime`` (photos)
    2. ``ffprobe`` ``creation_time`` tag (videos)
    3. File last-modified timestamp (fallback)
    """
    p = Path(path)
    media_type = get_media_type(p)

    if media_type == "photo":
        date = _extract_exif_date(p)
        if date:
            return date

    if media_type == "video":
        date = await _extract_ffprobe_date(p)
        if date:
            return date

    # Fallback for any media type
    return _mtime_date(p)


# ---------------------------------------------------------------------------
# GPS extraction
# ---------------------------------------------------------------------------


def _ratio_to_float(r) -> float:
    """Convert an exifread Ratio (or plain number) to a Python float."""
    try:
        return float(r.num) / float(r.den) if r.den else 0.0
    except AttributeError:
        return float(r)


def _dms_to_decimal(values: list, ref: str) -> float:
    """Convert a list of three DMS Ratio values + reference to decimal degrees."""
    d = _ratio_to_float(values[0])
    m = _ratio_to_float(values[1])
    s = _ratio_to_float(values[2])
    decimal = d + m / 60.0 + s / 3600.0
    return -decimal if ref in ("S", "W") else decimal


def get_gps_coords(path: str | Path) -> Optional[tuple[float, float]]:
    """Return *(lat, lon)* in decimal degrees if GPS EXIF is present, else ``None``.

    Only valid for photo files; videos are not supported.
    """
    p = Path(path)
    if get_media_type(p) != "photo":
        return None
    try:
        with p.open("rb") as fh:
            tags = exifread.process_file(fh, details=False)
        lat_tag = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon_tag = tags.get("GPS GPSLongitude")
        lon_ref = tags.get("GPS GPSLongitudeRef")
        if not (lat_tag and lat_ref and lon_tag and lon_ref):
            return None
        lat = _dms_to_decimal(lat_tag.values, str(lat_ref))
        lon = _dms_to_decimal(lon_tag.values, str(lon_ref))
        return (round(lat, 6), round(lon, 6))
    except Exception as exc:
        logger.debug("GPS extraction failed for %s: %s", path, exc)
        return None
