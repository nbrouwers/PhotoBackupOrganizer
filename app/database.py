"""Async SQLite persistence layer.

Two tables:
- ``processed_files`` – records every file that has been moved into the library.
  Prevents re-presenting already-handled files on subsequent scans (NFR-03).
- ``thumbnails`` – caches thumbnail/poster-frame paths so they are not
  regenerated on every scan (NFR-04).

The database is stored in the ``/cache`` volume alongside thumbnails so it
persists across container restarts without needing a dedicated bind mount.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from app.config import get_config

# Module-level connection shared for the lifetime of the process.
_db: Optional[aiosqlite.Connection] = None
_lock = asyncio.Lock()


async def _get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        async with _lock:
            if _db is None:
                db_path = Path(get_config().cache.path) / "photo_backup.db"
                db_path.parent.mkdir(parents=True, exist_ok=True)
                _db = await aiosqlite.connect(str(db_path))
                _db.row_factory = aiosqlite.Row
                await _initialise(_db)
    return _db


async def _initialise(db: aiosqlite.Connection) -> None:
    await db.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;

        CREATE TABLE IF NOT EXISTS processed_files (
            path        TEXT PRIMARY KEY,
            moved_to    TEXT NOT NULL,
            processed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS thumbnails (
            path        TEXT PRIMARY KEY,
            thumb_path  TEXT NOT NULL
        );
        """
    )
    await db.commit()


# ---------------------------------------------------------------------------
# processed_files helpers
# ---------------------------------------------------------------------------


async def mark_processed(source_path: str, destination_path: str) -> None:
    """Record that *source_path* was successfully moved to *destination_path*."""
    db = await _get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR REPLACE INTO processed_files (path, moved_to, processed_at) "
        "VALUES (?, ?, ?)",
        (source_path, destination_path, now),
    )
    await db.commit()


async def is_processed(source_path: str) -> bool:
    """Return ``True`` if *source_path* has already been moved."""
    db = await _get_db()
    async with db.execute(
        "SELECT 1 FROM processed_files WHERE path = ?", (source_path,)
    ) as cursor:
        return await cursor.fetchone() is not None


async def get_all_processed() -> list[dict]:
    """Return all processed file records, newest first."""
    db = await _get_db()
    async with db.execute(
        "SELECT path, moved_to, processed_at FROM processed_files "
        "ORDER BY processed_at DESC"
    ) as cursor:
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def unmark_processed(source_path: str) -> None:
    """Remove the processed record for *source_path* (used in tests)."""
    db = await _get_db()
    await db.execute("DELETE FROM processed_files WHERE path = ?", (source_path,))
    await db.commit()


# ---------------------------------------------------------------------------
# thumbnails helpers
# ---------------------------------------------------------------------------


async def get_cached_thumbnail(source_path: str) -> Optional[str]:
    """Return the cached thumbnail path, or ``None`` if not yet generated."""
    db = await _get_db()
    async with db.execute(
        "SELECT thumb_path FROM thumbnails WHERE path = ?", (source_path,)
    ) as cursor:
        row = await cursor.fetchone()
    return row["thumb_path"] if row else None


async def set_cached_thumbnail(source_path: str, thumb_path: str) -> None:
    db = await _get_db()
    await db.execute(
        "INSERT OR REPLACE INTO thumbnails (path, thumb_path) VALUES (?, ?)",
        (source_path, thumb_path),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def close_db() -> None:
    """Close the database connection gracefully (call on app shutdown)."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
