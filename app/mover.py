"""File move operations with dry-run and execute modes (FR-09, FR-11, FR-12, NFR-02).

Two public entry points:

- :func:`dry_run_batch` – simulates all move logic without touching the filesystem.
  Returns a :class:`DryRunResult` showing what *would* happen for each file.

- :func:`execute_batch` – performs the actual file moves.  Uses
  ``shutil.copy2`` to write the file then ``os.remove`` to delete the source
  *only after a confirmed successful write* (NFR-02).
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from app.database import mark_processed
from app.duplicates import is_duplicate

logger = logging.getLogger(__name__)

MoveAction = Literal["move", "skip_duplicate", "error"]


# ---------------------------------------------------------------------------
# Input / Output data structures
# ---------------------------------------------------------------------------


@dataclass
class MoveAssignment:
    """A single file→destination mapping provided by the UI."""

    src_path: str
    dest_dir: str  # Absolute path to the destination *directory*


@dataclass
class FileResult:
    src: str
    final_dest: str  # Full path including filename
    action: MoveAction
    original_filename: str
    final_filename: str
    conflict_note: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class DryRunResult:
    files: list[FileResult] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        counts: dict[str, int] = {"move": 0, "rename": 0, "skip_duplicate": 0, "error": 0}
        for f in self.files:
            counts[f.action] = counts.get(f.action, 0) + 1
        return counts


@dataclass
class BatchResult:
    files: list[FileResult] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        counts: dict[str, int] = {"move": 0, "rename": 0, "skip_duplicate": 0, "error": 0}
        for f in self.files:
            counts[f.action] = counts.get(f.action, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def _audit_log_path() -> Path:
    import os
    log_dir_str = os.environ.get("PHOTO_BACKUP_LOG_DIR", "")
    if log_dir_str:
        log_dir = Path(log_dir_str)
    else:
        # Derive from the configured cache path so local dev on Windows also
        # has a writable location (e.g. C:\Temp\pbo\logs next to .\cache).
        # In Docker the cache is /cache, so logs end up at /logs — same as before.
        from app.config import get_config
        log_dir = Path(get_config().cache.path).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "photo-backup-organizer.log"


def _write_audit_entry(result: FileResult) -> None:
    """Append a single line to the persistent audit log (NFR-05, FR-13)."""
    write_log_entry(
        action=result.action,
        src=result.src,
        dest=result.final_dest,
        note=result.conflict_note or "",
        error=result.error_message or "",
    )


def write_log_entry(
    action: str,
    src: str = "",
    dest: str = "",
    note: str = "",
    error: str = "",
) -> None:
    """Write a tab-separated entry to the persistent audit log.

    Public so that routers (scan, delete, etc.) can log non-move events.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _audit_log_path().open("a", encoding="utf-8") as fh:
            fh.write(f"{now}\t{action}\t{src}\t{dest}\t{note}\t{error}\n")
    except OSError as exc:
        logger.error("Failed to write audit log: %s", exc)


# ---------------------------------------------------------------------------
# Core per-file logic (shared between dry-run and execute)
# ---------------------------------------------------------------------------


def _simulate_file(src_path: str, dest_dir_str: str) -> FileResult:
    """Simulate the move for a single file without touching the filesystem."""
    src = Path(src_path)
    dest_dir = Path(dest_dir_str)
    original_filename = src.name
    candidate = dest_dir / original_filename

    # Skip when a file with the same name already exists at the destination,
    # regardless of content.  The user should review and resolve conflicts
    # manually rather than risk overwriting or creating confusing duplicates.
    if candidate.exists():
        return FileResult(
            src=src_path,
            final_dest=str(candidate),
            action="skip_duplicate",
            original_filename=original_filename,
            final_filename=original_filename,
            conflict_note="File with same name already exists at destination",
        )

    # Also skip when an identical file exists under a different name.
    if is_duplicate(src, dest_dir):
        return FileResult(
            src=src_path,
            final_dest=str(dest_dir / original_filename),
            action="skip_duplicate",
            original_filename=original_filename,
            final_filename=original_filename,
            conflict_note="Identical file already exists in destination (different name)",
        )

    return FileResult(
        src=src_path,
        final_dest=str(candidate),
        action="move",
        original_filename=original_filename,
        final_filename=original_filename,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def dry_run_batch(assignments: list[MoveAssignment]) -> DryRunResult:
    """Simulate all moves without touching the filesystem.

    Returns a :class:`DryRunResult` with per-file predicted actions, resolved
    destination paths, and any rename notes.
    """
    result = DryRunResult()
    for assignment in assignments:
        file_result = _simulate_file(assignment.src_path, assignment.dest_dir)
        result.files.append(file_result)
    return result


async def execute_batch(assignments: list[MoveAssignment]) -> BatchResult:
    """Execute the moves for all assignments.

    For each file:
    1. Check for duplicates → skip if found.
    2. Resolve filename collision.
    3. Ensure destination directory exists.
    4. ``shutil.copy2`` source → dest  (preserves timestamps).
    5. ``os.remove(src)`` **only** after copy succeeds (NFR-02).
    6. Record in DB and audit log.
    """
    result = BatchResult()

    for assignment in assignments:
        src = Path(assignment.src_path)
        dest_dir = Path(assignment.dest_dir)
        original_filename = src.name

        try:
            candidate = dest_dir / original_filename

            # Skip when a file with the same name already exists at destination.
            if candidate.exists():
                file_result = FileResult(
                    src=assignment.src_path,
                    final_dest=str(candidate),
                    action="skip_duplicate",
                    original_filename=original_filename,
                    final_filename=original_filename,
                    conflict_note="File with same name already exists at destination",
                )
                result.files.append(file_result)
                _write_audit_entry(file_result)
                continue

            # Skip when an identical file exists under a different name.
            if is_duplicate(src, dest_dir):
                file_result = FileResult(
                    src=assignment.src_path,
                    final_dest=str(dest_dir / original_filename),
                    action="skip_duplicate",
                    original_filename=original_filename,
                    final_filename=original_filename,
                    conflict_note="Identical file already exists in destination (different name)",
                )
                result.files.append(file_result)
                _write_audit_entry(file_result)
                continue

            # Create destination folder only when a file is actually being moved
            # (prevents empty folder creation for mirrored video dirs with no videos).
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Write first, delete only on success (NFR-02)
            shutil.copy2(str(src), str(candidate))
            os.remove(str(src))

            await mark_processed(assignment.src_path, str(candidate))

            file_result = FileResult(
                src=assignment.src_path,
                final_dest=str(candidate),
                action="move",
                original_filename=original_filename,
                final_filename=original_filename,
            )

        except Exception as exc:
            logger.error("Failed to move %s: %s", assignment.src_path, exc)
            file_result = FileResult(
                src=assignment.src_path,
                final_dest=str(dest_dir / original_filename),
                action="error",
                original_filename=original_filename,
                final_filename=original_filename,
                error_message=str(exc),
            )

        result.files.append(file_result)
        _write_audit_entry(file_result)

    return result
