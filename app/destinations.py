"""Library destination path management (FR-05 – FR-08, FR-18).

Provides helpers for:
- Resolving quarterly fallback paths (e.g. ``/photos/2026/Q1/``).
- Listing existing event categories and event folders.
- Creating new event folders on demand.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Literal

from app.config import get_config
from app.metadata import MediaType

logger = logging.getLogger(__name__)

Quarter = Literal["Q1", "Q2", "Q3", "Q4"]

# Synology NAS creates these special directories inside every indexed folder.
# Exclude them from event category / folder listings so they don't appear as
# destinations and so iterdir() doesn't traverse them unnecessarily.
_SYNOLOGY_SKIP = frozenset({"@eaDir", "@Recycle", "@Recently-Snapshot", "@tmp", "#recycle"})


def _quarter(d: date) -> Quarter:
    return f"Q{(d.month - 1) // 3 + 1}"  # type: ignore[return-value]


def _library_root(media_type: MediaType) -> Path:
    cfg = get_config()
    if media_type == "photo":
        return Path(cfg.library.photos_root)
    return Path(cfg.library.videos_root)


# ---------------------------------------------------------------------------
# Quarterly folders
# ---------------------------------------------------------------------------


def resolve_quarterly_path(media_type: MediaType, capture_date: date) -> Path:
    """Return the quarterly destination path for a given media type and date.

    Example: ``/photos/2026/Q1/``
    """
    return _library_root(media_type) / str(capture_date.year) / _quarter(capture_date)


def ensure_quarterly_folder(path: Path) -> None:
    """Create the quarterly folder (and any parent directories) if absent."""
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Event folders
# ---------------------------------------------------------------------------


def list_event_categories(media_type: MediaType) -> list[str]:
    """Return the first-level subdirectory names under the library root that
    look like event categories (i.e. are not year folders).

    Year folders and Synology internal directories are excluded.
    """
    root = _library_root(media_type)
    if not root.exists():
        return []
    try:
        return sorted(
            d.name
            for d in root.iterdir()
            if d.is_dir()
            and not d.name.isdigit()
            and d.name not in _SYNOLOGY_SKIP
        )
    except OSError as exc:
        logger.warning("Could not list event categories in %s: %s", root, exc)
        return []


def list_event_folders(media_type: MediaType, category: str) -> list[str]:
    """Return event folder names under ``<library_root>/<category>/``."""
    category_path = _library_root(media_type) / category
    if not category_path.exists():
        return []
    try:
        return sorted(
            d.name
            for d in category_path.iterdir()
            if d.is_dir() and d.name not in _SYNOLOGY_SKIP
        )
    except OSError as exc:
        logger.warning("Could not list event folders in %s: %s", category_path, exc)
        return []


def create_event_folder(media_type: MediaType, category: str, name: str) -> Path:
    """Create and return the path ``<library_root>/<category>/<name>/``.

    Creates any required intermediate directories (FR-07).
    Raises ``ValueError`` if the resulting path would escape the library root.
    """
    root = _library_root(media_type)
    target = (root / category / name).resolve()

    # Security: prevent path traversal
    if not str(target).startswith(str(root.resolve())):
        raise ValueError(
            f"Resolved path {target} is outside the library root {root}"
        )

    target.mkdir(parents=True, exist_ok=True)
    logger.info("Created event folder: %s", target)
    return target


def resolve_event_path(media_type: MediaType, category: str, name: str) -> Path:
    """Return the path for an event folder without creating it."""
    return _library_root(media_type) / category / name


# ---------------------------------------------------------------------------
# Direct child-folder helpers (for the manual destination picker)
# ---------------------------------------------------------------------------


def list_child_folders(media_type: MediaType) -> list[str]:
    """Return names of all first-level subdirectories under the library root.

    Synology internal directories and hidden dirs are excluded.
    """
    root = _library_root(media_type)
    if not root.exists():
        return []
    try:
        return sorted(
            d.name
            for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name not in _SYNOLOGY_SKIP
        )
    except OSError as exc:
        logger.warning("Could not list child folders in %s: %s", root, exc)
        return []


def list_subfolders_at(media_type: MediaType, rel_path: str = "") -> list[str]:
    """Return names of immediate subdirectories at ``<library_root>/<rel_path>``.

    Synology internal directories and hidden dirs are excluded.
    Security: *rel_path* is resolved against the library root and must not
    escape it.
    """
    root = _library_root(media_type).resolve()
    if rel_path:
        target = (root / rel_path.replace("\\", "/")).resolve()
        if not str(target).startswith(str(root)):
            raise ValueError(f"Path {rel_path!r} escapes the library root")
    else:
        target = root
    if not target.exists():
        return []
    try:
        return sorted(
            d.name
            for d in target.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name not in _SYNOLOGY_SKIP
        )
    except OSError as exc:
        logger.warning("Could not list subfolders in %s: %s", target, exc)
        return []


def ensure_folder_path(media_type: MediaType, rel_path: str) -> Path:
    """Create and return ``<library_root>/<rel_path>``.

    *rel_path* may contain forward slashes for nested creation.
    A ``ValueError`` is raised on empty input or path traversal.
    """
    if not rel_path or not rel_path.strip("/"):
        raise ValueError("rel_path must not be empty")
    root = _library_root(media_type).resolve()
    target = (root / rel_path.replace("\\", "/")).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Path {rel_path!r} escapes the library root")
    target.mkdir(parents=True, exist_ok=True)
    logger.info("Ensured destination folder: %s", target)
    return target


def ensure_child_folder(media_type: MediaType, name: str) -> Path:
    """Create and return ``<library_root>/<name>``.

    Raises ``ValueError`` if *name* contains path separators (prevents path
    traversal) or if the resolved path escapes the library root.
    """
    if not name or any(c in name for c in ("/", "\\", "..")):
        raise ValueError(f"Invalid folder name: {name!r}")
    root = _library_root(media_type)
    target = (root / name).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise ValueError(f"Resolved path {target} is outside the library root {root}")
    target.mkdir(parents=True, exist_ok=True)
    logger.info("Ensured destination folder: %s", target)
    return target


# ---------------------------------------------------------------------------
# Unified destination resolver
# ---------------------------------------------------------------------------


def resolve_destination(
    media_type: MediaType,
    *,
    dest_type: Literal["quarterly", "event"],
    capture_date: date | None = None,
    category: str | None = None,
    event_name: str | None = None,
) -> Path:
    """Return the destination directory path for a file.

    Args:
        media_type: ``"photo"`` or ``"video"``.
        dest_type: ``"quarterly"`` or ``"event"``.
        capture_date: Required when ``dest_type == "quarterly"``.
        category: Required when ``dest_type == "event"``.
        event_name: Required when ``dest_type == "event"``.
    """
    if dest_type == "quarterly":
        if capture_date is None:
            raise ValueError("capture_date is required for quarterly destinations")
        return resolve_quarterly_path(media_type, capture_date)

    if dest_type == "event":
        if not category or not event_name:
            raise ValueError("category and event_name are required for event destinations")
        return resolve_event_path(media_type, category, event_name)

    raise ValueError(f"Unknown dest_type: {dest_type!r}")
