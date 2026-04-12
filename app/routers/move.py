"""Move API router – dry-run and execute (FR-09, FR-11, FR-12, FR-20, NFR-02)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import get_config
from app.mover import MoveAssignment, dry_run_batch, execute_batch, write_log_entry

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
# Delete endpoint
# ---------------------------------------------------------------------------


class DeleteRequest(BaseModel):
    paths: list[str]


@router.post("/delete")
async def delete_files(req: DeleteRequest) -> dict:
    """Permanently delete source files by path.

    Each path is validated to be within a configured device source directory
    to prevent path traversal attacks.
    """
    if not req.paths:
        raise HTTPException(status_code=422, detail="No paths provided")

    cfg = get_config()
    allowed_roots = [Path(d.path).resolve() for d in cfg.devices]

    results: list[dict] = []
    for raw_path in req.paths:
        try:
            p = Path(raw_path).resolve()
        except Exception:
            results.append({"path": raw_path, "status": "error", "message": "Invalid path"})
            continue

        # Security: only allow deletion within configured device source directories
        if not any(p.is_relative_to(root) for root in allowed_roots):
            logger.warning("Delete attempt outside allowed roots: %s", p)
            results.append({"path": raw_path, "status": "error", "message": "Path not in a source directory"})
            continue

        try:
            p.unlink()
            logger.info("Deleted: %s", p)
            write_log_entry("delete", src=str(p))
            results.append({"path": raw_path, "status": "deleted"})
        except FileNotFoundError:
            results.append({"path": raw_path, "status": "not_found"})
        except OSError as exc:
            write_log_entry("delete_error", src=str(p), error=str(exc))
            results.append({"path": raw_path, "status": "error", "message": str(exc)})

    deleted = sum(1 for r in results if r["status"] == "deleted")
    return {"deleted": deleted, "total": len(req.paths), "results": results}


# ---------------------------------------------------------------------------
# Audit log endpoint
# ---------------------------------------------------------------------------


@router.get("/log")
async def get_log(lines: int = 200) -> dict:
    """Return the most recent *lines* entries from the persistent audit log."""
    import os
    from app.mover import _audit_log_path
    log_path = _audit_log_path()

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


@router.get("/log/rows", response_class=HTMLResponse)
async def get_log_rows(lines: int = 200) -> str:
    """Return audit log entries as HTML <tr> rows for HTMX injection."""
    from fastapi.responses import HTMLResponse as _HR
    data = await get_log(lines)
    entries = data["entries"]
    if not entries:
        return _HR('<tr><td colspan="5" style="text-align:center;color:var(--clr-text-3);padding:1.5rem;">No log entries yet.</td></tr>')

    _ACTION_BADGE = {
        "move":           "badge-move",
        "rename":         "badge-rename",
        "skip_duplicate": "badge-skip",
        "delete":         "badge-error",
        "delete_error":   "badge-error",
        "scan_start":     "badge-skip",
        "scan_complete":  "badge-move",
        "scan_error":     "badge-error",
    }

    def _esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rows = []
    for e in reversed(entries):   # newest first
        badge = _ACTION_BADGE.get(e["action"], "badge-error")
        note_or_error = e["error"] or e["note"]
        rows.append(
            f'<tr>'
            f'<td style="white-space:nowrap;font-size:.8rem;">{_esc(e["timestamp"])}</td>'
            f'<td><span class="badge {badge}">{_esc(e["action"])}</span></td>'
            f'<td style="font-size:.8rem;word-break:break-all;">{_esc(e["src"])}</td>'
            f'<td style="font-size:.8rem;word-break:break-all;">{_esc(e["dest"])}</td>'
            f'<td style="font-size:.8rem;">{_esc(note_or_error)}</td>'
            f'</tr>'
        )
    return _HR("\n".join(rows))

    return {"entries": entries}
