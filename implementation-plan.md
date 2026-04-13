# Photo Backup Organizer – Implementation Plan (rev. 2)

A Python/FastAPI application, served via HTMX + Jinja2, running in a Docker container on a Synology NAS. The user reviews unprocessed backup media in a web UI, assigns files to event or quarterly library folders, then triggers either a **dry-run** (preview of all filesystem changes) or an **actual move** (the real batch operation). An SQLite database tracks processed files for idempotent re-scanning.

---

## Technology Compatibility Review

The original stack is fully compatible with Synology NAS / DSM 7.x, with two important corrections:

**Base image: `python:3.12-slim-bookworm` (Debian Slim) instead of Alpine**
- Synology consumer NAS CPUs span `amd64` (Intel Celeron/Atom, AMD Ryzen — x20 series and newer) and `arm64` (Realtek RTD1619B on budget models like DS223/DS423). The `python:3.12-slim-bookworm` official image publishes multi-arch manifests for both `linux/amd64` and `linux/arm64`, so a single image tag works on all current hardware without adjustment.
- Pillow requires native C libraries (libjpeg, libpng, libwebp). On Alpine (musl libc), these must be compiled from source; on Debian Slim, pre-built wheels install correctly via `pip`. Alpine Pillow builds are a well-known pain point in constrained containers.
- `ffmpeg` from the Debian `bookworm` repo (`apt-get install ffmpeg`) ships with a broader patent-unencumbered codec set than Alpine community builds, including hardware-friendly codecs for H.264/HEVC common in phone recordings.
- `aiosqlite`, `exifread`, `PyYAML`, `FastAPI`, and `uvicorn` are pure-Python or have `manylinux` wheels — no compatibility issues on any architecture.

**`docker-compose` v2 on DSM 7.x Container Manager** — confirmed available. `docker compose up` works natively in Container Manager.

**No other tech stack changes required.** FastAPI, HTMX + Jinja2, aiosqlite, and Pillow are a proven, lightweight combination suitable for the 512 MB RAM constraint (NFR-07).

---

## Steps

### Phase 1 – Project Scaffold

1. Create the top-level directory layout:
   ```
   photo-backup-organizer/
   ├── app/
   │   ├── __init__.py
   │   ├── main.py
   │   ├── config.py
   │   ├── database.py
   │   ├── scanner.py
   │   ├── metadata.py
   │   ├── thumbnails.py
   │   ├── duplicates.py
   │   ├── mover.py
   │   ├── destinations.py
   │   ├── routers/
   │   │   ├── scan.py
   │   │   ├── destinations.py
   │   │   ├── move.py
   │   │   └── ui.py
   │   └── templates/
   │       ├── base.html
   │       ├── index.html
   │       ├── review.html
   │       ├── confirm.html
   │       └── log.html
   ├── config.example.yaml
   ├── Dockerfile
   ├── docker-compose.yml
   ├── pyproject.toml
   └── tests/
   ```
2. Write `pyproject.toml` declaring dependencies: `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `aiosqlite`, `Pillow`, `exifread`, `PyYAML`, `pydantic`, `httpx` (for tests).
3. Write a multi-stage `Dockerfile`:
   - **Builder stage**: `python:3.12-slim-bookworm`, installs Python deps into a venv.
   - **Runtime stage**: `python:3.12-slim-bookworm`, installs `ffmpeg` via `apt-get`, copies the venv from the builder.
4. Write `docker-compose.yml` with bind mounts for `/config`, `/backups`, `/photos`, `/videos`, `/logs`, and `/cache`.

---

### Phase 2 – Configuration

5. Design `config.example.yaml` covering all FR-22/FR-23 knobs.
6. Implement `app/config.py`: load and validate YAML with pydantic; expose `get_config()` singleton.

---

### Phase 3 – Persistence & State (NFR-03)

7. Implement `app/database.py` using `aiosqlite`. Tables:
   - `processed_files(path TEXT PRIMARY KEY, moved_to TEXT, processed_at TEXT)`
   - `thumbnails(path TEXT PRIMARY KEY, thumb_path TEXT)`
8. Expose async helpers: `mark_processed()`, `is_processed()`, `get_all_processed()`.

---

### Phase 4 – Scanner & Metadata (FR-01–FR-04, FR-10)

9. Implement `app/scanner.py`: `scan_all_devices()` recurses device backup folders, filters by configured extensions, skips already-processed files, returns `MediaFile` objects grouped by device label and capture date.
   - `ScanProgress.cancelled` flag — set via `request_cancel()`; checked between files in `_scan_device` and between devices in `scan_all_devices`. Scan stops cleanly without a server restart.
   - `ScanProgress.device_counts` — accumulates `{label, found}` as each device finishes; exposed in `to_dict()` and rendered in the progress panel and the completion banner.
   - `POST /api/scan/cancel` — sets the cancellation flag; returns `{status: "cancelling"}` immediately.
10. Implement `app/metadata.py`:
    - `get_capture_date(path)` — `exifread` for photos; `ffprobe` for videos; fallback to `os.path.getmtime`.
    - `get_media_type(path)` — classify as `photo` or `video` by extension.

---

### Phase 5 – Thumbnails (FR-19, NFR-04)

11. Implement `app/thumbnails.py`:
    - `generate_photo_thumbnail(path)` — Pillow, 300×300 JPEG, stored in `/cache` volume.
    - `generate_video_poster(path)` — `ffmpeg -ss 00:00:01 -vframes 1`.
    - Both check DB before regenerating.
    - `probe_video_codec(path)` — `ffprobe -select_streams v:0 -show_entries stream=codec_name`; returns e.g. `"h264"` or `None`.
    - `is_browser_native_codec(codec)` — returns `True` for h264/vp8/vp9/av1/avc1.
    - `generate_video_preview(path)` — if codec is browser-native, returns `source_path` unchanged (fast path); otherwise transcodes to H.264 and caches the result.

---

### Phase 6 – Destination Logic (FR-05–FR-10, FR-23)

12. Implement `app/destinations.py`:
    - `_library_root(media_type)` — resolve photos or videos root from config.
    - `list_subfolders_at(media_type, rel_path)` — return immediate subdirectory names at any depth, path-traversal protected.
    - `ensure_folder_path(media_type, rel_path)` — create a folder at an arbitrary forward-slash-separated relative path; raises `ValueError` on traversal or empty input.
    - `count_files_at(media_type, rel_path)` — count non-hidden files at a given path; used by the destination zone badge.
    - Legacy helpers kept for backward compatibility: `list_event_categories`, `list_event_folders`, `create_event_folder`, `resolve_quarterly_path`.

---

### Phase 7 – Duplicate Detection & File Mover (FR-11–FR-16, NFR-02)

13. Implement `app/duplicates.py`: `file_hash(path)`, `is_duplicate(src, dest_dir)`.
14. Implement `app/mover.py` with two entry points:

    **`dry_run_batch(assignments) → DryRunResult`**
    - Simulates resolution logic: duplicate detection, same-name collision detection.
    - Does **not** touch the filesystem.
    - Returns per-file entries: `{src, resolved_dest, action, final_filename, conflict_note}`.
    - Actions: `move`, `skip_duplicate`, `skip` (same-name collision), `error`.

    **`execute_batch(assignments) → BatchResult`**
    - Creates destination folder at move time only (FR-08/lazy creation).
    - `shutil.copy2` to destination; `os.remove(src)` only on success (NFR-02).
    - Calls `mark_processed()` in DB; writes audit log entry via `write_log_entry()`.
    - `write_log_entry(event, src, dest, note)` — public helper for scan and delete events.

---

### Phase 8 – API Routes

15. `app/routers/scan.py`:
    - `POST /api/scan` — trigger background scan, log start/complete/error events
    - `GET /api/scan/status` — poll scan progress
    - `GET /api/scan/result` — retrieve last scan result
    - `GET /api/scan/folders` — list scannable sub-folders per device
16. `app/routers/destinations.py`:
    - `GET /api/destinations/folder-children?root=&path=` — lazy-load tree children
    - `GET /api/destinations/folder-count?root=&path=` — existing file count for zone badge
    - `POST /api/destinations/ensure-folder` — create folder at arbitrary nested path
    - Legacy endpoints retained: `/categories`, `/events`, `/child-folders`
17. `app/routers/move.py`:
    - `POST /api/move/dry-run` — returns `DryRunResult`, no filesystem changes
    - `POST /api/move/execute` — moves files, returns `BatchResult`
    - `POST /api/move/delete` — permanently delete source files by path list
    - `GET /api/move/log` — recent audit log entries (JSON)
    - `GET /api/move/log/rows` — audit log as HTML rows (HTMX); accepts `?action=` substring filter so the log page can show only errors, skips, etc. without a page reload
    - Module-level `_esc()` helper shared by row rendering and filter/copy-button generation
18. `app/routers/ui.py`: HTML page routes via Jinja2, `/thumbnails`, `/video-preview`, `/media`, `/api/geocode`

---

### Phase 9 – Web UI

19. **`index.html`** — scan trigger with HTMX polling; two-phase progress bar; scan button race-condition fix: polls `/api/scan/status` until `running=True` before loading progress partial.
20. **`review.html`** — full drag-and-drop review page:
    - Sticky top bar with Delete, Quick-assign, Dry-run, and Move buttons visible while scrolling.
    - `FolderPicker` class: lazy-expanding tree, inline folder creation at any depth, selection tracking, localStorage persistence.
    - Destination zone badge: shows `📸 existing+pending  🏂 existing+pending` counts, fetched asynchronously.
    - Dry-run result rendered inline with Confirm & Move button and animated progress bar.
    - Full-screen lightbox with ‹/› navigation, keyboard shortcuts, and 🗑 delete button.
    - Source filter dropdown and sort controls.
    - Tile-size slider (2–10 columns).
    - Bulk delete with confirmation.
    - **Keyboard zone shortcuts (1–9)**: pressing a digit assigns all selected cards to the matching zone; zone badges display their shortcut number.
    - **Date-group headers**: each device·date group has a `Select all` button that selects every visible card in that group.
    - **Ctrl+Z undo**: all assignment paths (drag-drop, keyboard, quick-assign, badge unassign) funnel through `_applyAssignments`/`pushUndo`; up to 50 undo levels.
    - **Quick-assign button + `Q` shortcut**: appears in the top bar after the first assignment; re-assigns selected cards to the last-used zone.
21. **`log.html`** — audit log table, live-updated via HTMX polling of `/api/move/log/rows`.
    - **Action filter bar**: one-click buttons (All / Moves / Skips / Errors / Deletes / Scan events) each trigger an HTMX reload of `#log-table-body` with the corresponding `?action=` param.
    - **Copy-to-clipboard button**: each non-empty source and destination path cell displays a 📋 button; clicking it writes the path to the clipboard (`navigator.clipboard` with `execCommand` fallback).
22. `confirm.html` retained as a legacy stub; dry-run confirmation is now inline in `review.html`.

---

### Phase 10 – Security & Hardening (NFR-06)

23. Optional HTTP Basic Auth FastAPI middleware, enabled when `security.basic_auth` is set in config.
    All destination and file-path parameters are resolved against the library root and rejected on traversal attempts.

---

### Phase 11 – Tests

24. Unit tests: `config.py`, `metadata.py`, `duplicates.py`, `mover.py`, `destinations.py`.
25. 48 tests passing; covers scan, destination listing/creation, duplicate detection, dry-run and execute batch logic, file counting, and delete operations.

---

## Key Decisions

- **Cooperative cancellation via flag** — `ScanProgress.cancelled` is a plain boolean checked between files and between devices; no threads, asyncio cancellation tokens, or OS signals needed. Simple and safe with FastAPI background tasks.
- **`python:3.12-slim-bookworm`** — eliminates Pillow compilation friction; covers amd64 and arm64 NAS hardware.
- **Multi-arch Docker build** — single image tag runs on all current Synology NAS CPUs.
- **Pillow removed; ffmpeg only** — thumbnails, video posters, and H.264 previews are all generated via `ffmpeg` subprocess. Removes a binary-dependency pain point.
- **Native-codec fast path for video preview** — `ffprobe` checks the video codec before any transcoding. Browser-native codecs (H.264/VP8/VP9/AV1) are served via HTTP 302 redirect to `/media` with zero transcoding overhead. HEVC is still transcoded once and cached.
- **Three move endpoints** — dry-run and execute are separate, explicit API calls.
- **Same-name collision = skip (not rename)** — avoids silent data mutation; the user must resolve the conflict intentionally.
- **Lazy folder creation** — destination folders are only created at move time, never speculatively. Preserves a clean library even when operations are cancelled.
- **`FolderPicker` tree UI** — lazy-loading JS class replaces flat dropdown; supports arbitrary nesting, inline creation at any depth, and re-expansion of newly created nodes.
- **Destination file counts** — `GET /api/destinations/folder-count` drives the zone badge; gives immediate context about how full a destination already is.
- **Single assignment engine (`_applyAssignments`)** — all assignment paths (drag-drop, keyboard shortcut, quick-assign) share one function so undo snapshots, zone counts, and last-used tracking are always consistent.
- **Audit log extended** — scan start/complete/error and delete events are all written via `write_log_entry()`, alongside move events.
- **SQLite** — efficient `is_processed()` lookups; persistent across container restarts.
- **HTMX + Jinja2** — no JS build pipeline; lightweight.
- **`shutil.copy2` + `os.remove`** — explicit write-first, delete-on-success contract; safe across NAS volumes.
