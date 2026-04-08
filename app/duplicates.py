"""Duplicate file detection (FR-11).

Uses a two-step approach to avoid full hash computation on every candidate:
1. Find files in the destination directory with the same size.
2. Compute SHA-256 of the source file and compare against those candidates.

A file is considered a duplicate when a destination file has the same size
AND the same SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 65_536  # 64 KB read chunks


def file_hash(path: str | Path) -> str:
    """Return the SHA-256 hex digest of a file, reading in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def is_duplicate(src_path: str | Path, dest_dir: str | Path) -> bool:
    """Return ``True`` if an identical file already exists in *dest_dir*.

    Identical means: same file size **and** same SHA-256 digest.
    Returns ``False`` if *dest_dir* does not exist.
    """
    src = Path(src_path)
    dest = Path(dest_dir)

    if not dest.exists():
        return False

    try:
        src_size = src.stat().st_size
    except OSError:
        return False

    # Only hash source once; compare against size-matched candidates
    src_digest: str | None = None
    for candidate in dest.iterdir():
        if not candidate.is_file():
            continue
        try:
            if candidate.stat().st_size != src_size:
                continue
            # Lazy-compute source hash on first match
            if src_digest is None:
                src_digest = file_hash(src)
            if file_hash(candidate) == src_digest:
                logger.debug("Duplicate detected: %s == %s", src, candidate)
                return True
        except OSError as exc:
            logger.debug("Could not read candidate %s: %s", candidate, exc)
            continue

    return False
