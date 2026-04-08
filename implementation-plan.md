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
10. Implement `app/metadata.py`:
    - `get_capture_date(path)` — `exifread` for photos; `ffprobe` for videos; fallback to `os.path.getmtime`.
    - `get_media_type(path)` — classify as `photo` or `video` by extension.

---

### Phase 5 – Thumbnails (FR-19, NFR-04)

11. Implement `app/thumbnails.py`:
    - `generate_photo_thumbnail(path)` — Pillow, 300×300 JPEG, stored in `/cache` volume.
    - `generate_video_poster(path)` — `ffmpeg -ss 00:00:01 -vframes 1`.
    - Both check DB before regenerating.

---

### Phase 6 – Destination Logic (FR-05–FR-08, FR-18)

12. Implement `app/destinations.py`:
    - `resolve_quarterly_path(media_type, capture_date)` → `<root>/<year>/Q<quarter>/`
    - `list_event_categories()`, `list_event_folders(category)`, `create_event_folder(...)`, `ensure_quarterly_folder(path)`.

---

### Phase 7 – Duplicate Detection & File Mover (FR-09, FR-11, FR-12, NFR-02)

13. Implement `app/duplicates.py`: `file_hash(path)`, `is_duplicate(src, dest_dir)`.
14. Implement `app/mover.py` with two entry points:

    **`dry_run_batch(assignments) → DryRunResult`**
    - Simulates all resolution logic (duplicate detection, filename collision resolution).
    - Does **not** touch the filesystem.
    - Returns per-file entries: `{src, resolved_dest, action, final_filename, conflict_note}`.

    **`execute_batch(assignments) → BatchResult`**
    - `shutil.copy2` to destination; `os.remove(src)` only on success (NFR-02).
    - Calls `mark_processed()` in DB; writes audit log entry.

---

### Phase 8 – API Routes

15. `app/routers/scan.py`: `GET /api/scan`, `GET /api/scan/status`
16. `app/routers/destinations.py`: category/event listing and creation, quarterly path calculation
17. `app/routers/move.py`:
    - `POST /api/move/dry-run` — returns `DryRunResult`, no filesystem changes
    - `POST /api/move/execute` — actually moves files, returns `BatchResult`
    - `GET /api/move/log` — recent audit log entries
18. `app/routers/ui.py`: HTML page routes via Jinja2

---

### Phase 9 – Web UI

19. **`index.html`** — scan trigger, HTMX polling
20. **`review.html`** — grouped file list, destination picker, thumbnail previews, "Preview changes" and "Move now" buttons
21. **`confirm.html`** — dry-run result table with "Confirm & Move" and "Back to review"
22. **`log.html`** — batch result summary and detail table

---

### Phase 10 – Security & Hardening (NFR-06)

23. Optional HTTP Basic Auth FastAPI middleware, enabled when `security.basic_auth` is set.

---

### Phase 11 – Tests

24. Unit tests: `config.py`, `metadata.py`, `duplicates.py`, `mover.py`, `destinations.py`.
25. End-to-end integration test: scan → dry-run → execute → verify file at destination, absent from source.

---

## Key Decisions

- **`python:3.12-slim-bookworm`** — eliminates Pillow compilation friction; covers amd64 and arm64 NAS hardware.
- **Multi-arch Docker build** — single image tag runs on all current Synology NAS CPUs.
- **Three move endpoints** — dry-run and execute are separate, explicit API calls.
- **"Move now" shortcut** — bypasses dry-run for power users; dry-run via confirm screen is the default path.
- **SQLite** — efficient `is_processed()` lookups; persistent across container restarts.
- **HTMX + Jinja2** — no JS build pipeline; lightweight.
- **`shutil.copy2` + `os.remove`** — explicit write-first, delete-on-success contract; safe across NAS volumes.
