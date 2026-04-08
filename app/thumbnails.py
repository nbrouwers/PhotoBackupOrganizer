"""Thumbnail and video poster-frame generation (FR-19, NFR-04).

Photos: resized via Pillow to a square JPEG (max thumb_size × thumb_size).
Videos: a single frame extracted at the 1-second mark by ``ffmpeg``.

Generated files are stored in ``<cache_path>/thumbs/`` and their paths are
cached in the SQLite ``thumbnails`` table so they are not regenerated on
every scan.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

from app.config import get_config
from app.database import get_cached_thumbnail, set_cached_thumbnail

logger = logging.getLogger(__name__)


def _thumb_dir() -> Path:
    cfg = get_config()
    d = Path(cfg.cache.path) / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _thumb_filename(source_path: str) -> str:
    """Derive a stable, unique thumbnail filename from the source path."""
    digest = hashlib.sha256(source_path.encode()).hexdigest()[:16]
    return f"{digest}.jpg"


# ---------------------------------------------------------------------------
# Photo thumbnails
# ---------------------------------------------------------------------------


def _generate_photo_thumb_sync(source_path: Path, dest_path: Path, size: int) -> None:
    """Blocking Pillow operation – run in a thread pool executor."""
    with Image.open(source_path) as img:
        img = img.convert("RGB")  # Handle HEIC/PNG with alpha
        img.thumbnail((size, size), Image.LANCZOS)
        img.save(dest_path, "JPEG", quality=75, optimize=True)


async def generate_photo_thumbnail(source_path: str) -> Optional[str]:
    """Return the path to the thumbnail JPEG for *source_path*.

    Checks the DB cache first; generates and caches if not found.
    Returns ``None`` on failure.
    """
    cached = await get_cached_thumbnail(source_path)
    if cached and Path(cached).exists():
        return cached

    cfg = get_config()
    dest_path = _thumb_dir() / _thumb_filename(source_path)

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            _generate_photo_thumb_sync,
            Path(source_path),
            dest_path,
            cfg.cache.thumb_size,
        )
        await set_cached_thumbnail(source_path, str(dest_path))
        return str(dest_path)
    except Exception as exc:
        logger.warning("Thumbnail generation failed for %s: %s", source_path, exc)
        return None


# ---------------------------------------------------------------------------
# Video poster-frame
# ---------------------------------------------------------------------------


async def generate_video_poster(source_path: str) -> Optional[str]:
    """Extract a single frame at 00:00:01 from a video file using ``ffmpeg``.

    Returns the path to the generated JPEG, or ``None`` on failure.
    """
    cached = await get_cached_thumbnail(source_path)
    if cached and Path(cached).exists():
        return cached

    dest_path = _thumb_dir() / _thumb_filename(source_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",                    # Overwrite without asking
            "-ss", "00:00:01",
            "-i", source_path,
            "-vframes", "1",
            "-q:v", "5",             # JPEG quality scale (2=best, 31=worst)
            "-vf", f"scale='min(300,iw)':-1",
            str(dest_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)

        if dest_path.exists():
            await set_cached_thumbnail(source_path, str(dest_path))
            return str(dest_path)

    except Exception as exc:
        logger.warning("Video poster generation failed for %s: %s", source_path, exc)

    return None


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------


async def get_thumbnail(source_path: str, media_type: str) -> Optional[str]:
    """Return a thumbnail path for any supported media type."""
    if media_type == "photo":
        return await generate_photo_thumbnail(source_path)
    if media_type == "video":
        return await generate_video_poster(source_path)
    return None
