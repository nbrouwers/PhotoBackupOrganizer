"""Move API router – dry-run and execute (FR-09, FR-11, FR-12, FR-20, NFR-02)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mover import MoveAssignment, dry_run_batch, execute_batch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/move", tags=["move"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AssignmentRequest(BaseModel):
    src_path: str
    dest_dir: str


class BatchRequest(BaseModel):
    assignments: list[AssignmentRequest]


def _assignment_list(req: BatchRequest) -> list[MoveAssignment]:
    return [MoveAssignment(src_path=a.src_path, dest_dir=a.dest_dir) for a in req.assignments]


def _file_result_dict(fr) -> dict:
    return {
        "src": fr.src,
        "final_dest": fr.final_dest,
        "action": fr.action,
        "original_filename": fr.original_filename,
        "final_filename": fr.final_filename,
        "conflict_note": fr.conflict_note,
        "error_message": fr.error_message,
    }


# ---------------------------------------------------------------------------
# Dry-run endpoint
# ---------------------------------------------------------------------------


@router.post("/dry-run")
async def dry_run(req: BatchRequest) -> dict:
    """Simulate all moves and return a preview.

    No filesystem changes are made (FR-20).
    """
    if not req.assignments:
        raise HTTPException(status_code=422, detail="No assignments provided")

    result = dry_run_batch(_assignment_list(req))
    return {
        "summary": result.summary,
        "files": [_file_result_dict(f) for f in result.files],
    }


# ---------------------------------------------------------------------------
# Execute endpoint
# ---------------------------------------------------------------------------


@router.post("/execute")
async def execute(req: BatchRequest) -> dict:
    """Execute all moves and return the outcome (FR-09).

    Files are only deleted from the source after a confirmed successful write
    to the destination (NFR-02).
    """
    if not req.assignments:
        raise HTTPException(status_code=422, detail="No assignments provided")

    result = await execute_batch(_assignment_list(req))
    return {
        "summary": result.summary,
        "files": [_file_result_dict(f) for f in result.files],
    }


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------


@router.get("/log")
async def get_log(lines: int = 200) -> dict:
    """Return the most recent *lines* entries from the persistent audit log."""
    import os
    log_path = Path(os.environ.get("PHOTO_BACKUP_LOG_DIR", "/logs")) / "photo-backup-organizer.log"

    if not log_path.exists():
        return {"entries": []}

    with log_path.open("r", encoding="utf-8") as fh:
        all_lines = fh.readlines()

    recent = all_lines[-lines:]
    entries = []
    for line in recent:
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 4:
            entries.append({
                "timestamp": parts[0],
                "action": parts[1],
                "src": parts[2],
                "dest": parts[3],
                "note": parts[4] if len(parts) > 4 else "",
                "error": parts[5] if len(parts) > 5 else "",
            })

    return {"entries": entries}
