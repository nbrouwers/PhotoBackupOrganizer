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

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:  # ImportError if not installed; OSError/RuntimeError if libheif missing
    pass

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

    Strategy:
    1. Return from DB cache if available.
    2. Generate via Pillow (fast, handles JPEG/PNG/WebP/HEIC with pillow-heif).
    3. Fall back to ffmpeg if Pillow cannot open the file (e.g. DNG/RAW,
       unusual HEIC variants, corrupted EXIF, etc.).
    """
    cached = await get_cached_thumbnail(source_path)
    if cached and Path(cached).exists():
        return cached

    cfg = get_config()
    dest_path = _thumb_dir() / _thumb_filename(source_path)
    size = cfg.cache.thumb_size

    # ── Primary: Pillow ────────────────────────────────────────────────────
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            _generate_photo_thumb_sync,
            Path(source_path),
            dest_path,
            size,
        )
        if dest_path.exists() and dest_path.stat().st_size > 0:
            await set_cached_thumbnail(source_path, str(dest_path))
            return str(dest_path)
    except Exception as exc:
        logger.info(
            "Pillow thumbnail failed for %s: %s — trying ffmpeg fallback",
            source_path, exc,
        )

    # ── Fallback: ffmpeg ───────────────────────────────────────────────────
    # Handles formats Pillow can't: DNG/RAW, some HEIC variants, etc.
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", source_path,
            "-vframes", "1",
            "-vf", f"scale='min({size},iw)':-2",
            str(dest_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)
        if dest_path.exists() and dest_path.stat().st_size > 0:
            await set_cached_thumbnail(source_path, str(dest_path))
            return str(dest_path)
    except Exception as exc:
        logger.warning(
            "ffmpeg thumbnail fallback also failed for %s: %s",
            source_path, exc,
        )

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
            "-vf", "scale='min(300,iw)':-2",   # -2 keeps even pixel dimensions
            str(dest_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=30)

        if dest_path.exists() and dest_path.stat().st_size > 0:
            await set_cached_thumbnail(source_path, str(dest_path))
            return str(dest_path)

    except Exception as exc:
        logger.warning("Video poster generation failed for %s: %s", source_path, exc)

    return None


# ---------------------------------------------------------------------------
# Video H.264 preview clip
# ---------------------------------------------------------------------------


async def generate_video_preview(source_path: str) -> Optional[str]:
    """Generate a short (max 15 s) H.264/AAC MP4 preview of *source_path*.

    The preview is transcoded by ffmpeg so it plays in all modern browsers,
    including those without HEVC/H.265 support (Chrome, Firefox on Linux).
    Results are cached; the first call blocks for 5–30 s depending on CPU
    speed and source length.

    Returns the path to the preview ``.mp4``, or ``None`` on failure.
    """
    cache_key = f"preview:{source_path}"
    cached = await get_cached_thumbnail(cache_key)
    if cached and Path(cached).exists():
        return cached

    raw_name = _thumb_filename(source_path)          # e.g. "abc123def456.jpg"
    preview_name = raw_name.replace(".jpg", "_preview.mp4")
    dest_path = _thumb_dir() / preview_name

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", source_path,
            "-t", "15",                          # first 15 seconds only
            "-vf", "scale='min(854,iw)':-2",     # max 480p-ish width; -2 keeps even dims
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-movflags", "+faststart",           # allow streaming before full download
            str(dest_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=120)

        if dest_path.exists() and dest_path.stat().st_size > 0:
            await set_cached_thumbnail(cache_key, str(dest_path))
            logger.debug("Video preview generated: %s", dest_path)
            return str(dest_path)

    except Exception as exc:
        logger.warning("Video preview generation failed for %s: %s", source_path, exc)

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
