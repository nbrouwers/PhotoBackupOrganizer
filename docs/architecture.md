# Photo Backup Organizer – Architecture

## Overview

Photo Backup Organizer is a **Python 3.12 / FastAPI** web application that runs as a single
Docker container on a Synology NAS. It reads media from per-device backup folders, presents
them in a browser-based review UI, and moves accepted files into a centrally organised library.

---

## System context

```
┌───────────────────────────────────────────────────────────────────┐
│  Synology NAS (DSM 7.x)                                           │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Docker container  (photo-backup-organizer)              │    │
│  │                                                          │    │
│  │   ┌────────────────────────────────────────────────┐    │    │
│  │   │  FastAPI / Uvicorn (port 8000)                 │    │    │
│  │   │  app/main.py  ──  app/routers/*                │    │    │
│  │   └───────────────────┬────────────────────────────┘    │    │
│  │                       │ calls                            │    │
│  │   ┌───────────────────▼───────────────────────────────┐ │    │
│  │   │  Core modules                                     │ │    │
│  │   │  config · database · scanner · metadata           │ │    │
│  │   │  thumbnails · duplicates · mover · destinations   │ │    │
│  │   └───────────────────────────────────────────────────┘ │    │
│  │                                                          │    │
│  │  ── bind mounts ─────────────────────────────────────── │    │
│  │   /config   /backups   /photos   /videos                │    │
│  │   /logs     /cache                                      │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                   │
│  SQLite DB  (/cache/pbo.db)                                       │
│  ffmpeg / ffprobe  (installed in image)                           │
└───────────────────────────────────────────────────────────────────┘

Browser (local network)  ◄──────── HTTP/8000 ──────────► FastAPI
```

---

## Runtime layers

### 1. Configuration — `app/config.py`

Reads a YAML file whose path comes from the `PHOTO_BACKUP_CONFIG` environment variable
(default `/config/config.yaml`). Produces a validated `AppConfig` singleton via
`get_config()` (backed by `functools.lru_cache`). All other modules call `get_config()`
to resolve paths and settings; nothing is hard-coded.

Key configuration objects:
| Object | Purpose |
|---|---|
| `DeviceConfig` | label + absolute path for each backup source device |
| `LibraryConfig` | photos\_root, videos\_root |
| `SecurityConfig` | optional HTTP Basic Auth credentials |

---

### 2. Persistence — `app/database.py`

Single **aiosqlite** database at `/cache/pbo.db`. Two tables:

| Table | Columns | Purpose |
|---|---|---|
| `processed_files` | `path, moved_to, processed_at` | Tracks files already moved so re-scans skip them |
| `geocode_cache` | `lat_lon, result, cached_at` | Caches OpenStreetMap reverse-geocode responses |

Async helpers: `mark_processed()`, `is_processed()`, `get_geocode_cache()`, `set_geocode_cache()`.

---

### 3. Scanner — `app/scanner.py`

```
scan_all_devices()
  └─ _scan_device(device)
       ├─ recurse backup subfolders
       ├─ is_processed() — skip already-moved files
       ├─ get_capture_date() / get_media_type()  (metadata.py)
       └─ yield MediaFile  →  grouped into ScanResult
```

`ScanProgress` is a module-level singleton written by the background task and polled by
`GET /api/scan/status`. It carries:
- `running`, `total`, `found`, `current_file` — for the live progress bar
- `device_counts` — per-device file counts shown in the done banner
- `cancelled` flag — set by `POST /api/scan/cancel`; checked between files

---

### 4. Metadata — `app/metadata.py`

| Function | Source | Fallback |
|---|---|---|
| `get_capture_date(path)` | EXIF (`exifread`) for photos; `ffprobe` for video | `os.path.getmtime` |
| `get_media_type(path)` | file extension | — |
| `get_gps(path)` | EXIF GPS tags | `None` |

---

### 5. Thumbnails & previews — `app/thumbnails.py`

All image and video work goes through **ffmpeg / ffprobe** subprocesses (no Pillow).

| Function | What it does |
|---|---|
| `generate_photo_thumbnail(path)` | `ffmpeg` scale to 300×300 JPEG, stored in `/cache` |
| `generate_video_poster(path)` | `ffmpeg -ss 1 -vframes 1` JPEG |
| `probe_video_codec(path)` | `ffprobe` — returns codec name string |
| `is_browser_native_codec(codec)` | `True` for h264 / vp8 / vp9 / av1 |
| `generate_video_preview(path)` | Fast path: returns source path if native codec; otherwise transcodes to H.264 and caches |

---

### 6. Destinations — `app/destinations.py`

Single source of truth for all library path operations. Routers never build raw paths.

| Function | Description |
|---|---|
| `list_subfolders_at(media_type, rel_path)` | Immediate children at any depth (path-traversal protected) |
| `ensure_folder_path(media_type, rel_path)` | Create nested folder; raises on traversal or empty input |
| `count_files_at(media_type, rel_path)` | Count of non-hidden files; drives zone badge counts |
| `_library_root(media_type)` | Resolve `photos_root` or `videos_root` from config |

Path safety: every supplied path is `.resolve()`d and asserted to start with the resolved library root before any filesystem operation.

---

### 7. Duplicate detection — `app/duplicates.py`

| Function | Description |
|---|---|
| `file_hash(path)` | SHA-256 of a file (chunked, memory-safe) |
| `is_duplicate(src, dest_dir)` | `True` if a file with the same size + hash exists in `dest_dir` |

Used by `dry_run_batch` and `execute_batch` to skip identical files.

---

### 8. Mover — `app/mover.py`

Two public entry points:

**`dry_run_batch(assignments) → DryRunResult`**
- Resolves each `(src, dest_dir)` pair: detects duplicates, same-name collisions
- Returns a list of per-file entries with `action ∈ {move, skip_duplicate, skip, error}`
- No filesystem changes

**`execute_batch(assignments) → BatchResult`**
- Creates destination folder at move time only (lazy creation — FR-08)
- `shutil.copy2(src, dest)` then `os.remove(src)` only on success
- Calls `mark_processed()` and `write_log_entry()` for every file

**`write_log_entry(event, src, dest, note)`** — shared helper used by scan, delete, and move events to append a row to the SQLite audit log.

---

### 9. API routers

| Router file | Prefix | Key endpoints |
|---|---|---|
| `routers/scan.py` | `/api/scan` | `POST /` trigger scan, `GET /status`, `GET /result`, `GET /folders`, `GET /available-quarters`, `POST /cancel` |
| `routers/destinations.py` | `/api/destinations` | `GET /folder-children`, `GET /folder-count`, `POST /ensure-folder` |
| `routers/move.py` | `/api/move` | `POST /dry-run`, `POST /execute`, `POST /delete`, `GET /log`, `GET /log/rows` |
| `routers/ui.py` | `/` | Page routes (Jinja2), `GET /thumbnails`, `GET /video-preview`, `GET /media`, `GET /api/geocode` |

All request bodies are validated with **Pydantic** models. HTML-fragment endpoints
(`/api/move/log/rows`, partial templates) return `HTMLResponse` for HTMX consumption.

---

### 10. Web UI — `app/templates/`

The UI is server-rendered **Jinja2 + HTMX** — no JS build pipeline.

| Template | Route | Purpose |
|---|---|---|
| `base.html` | — | Shared layout, nav, CSS custom properties |
| `index.html` | `GET /` | Scan page — trigger scan, date presets, two-phase progress bar |
| `review.html` | `GET /review` | Review page — media grid, destination panel, lightbox |
| `log.html` | `GET /log` | Audit log with action filter bar |
| `confirm.html` | — | Legacy stub (confirmation now inline in `review.html`) |

`review.html` has the largest client-side footprint:
- Module-level `let` variables hold all mutable state (selection set, undo stack, zone list, last-used zone)
- `FolderPicker` class — lazy-expanding tree, inline folder creation, localStorage persistence
- `_applyAssignments()` — single assignment engine shared by drag-drop, keyboard shortcuts, quick-assign
- `syncGroupCheckboxes()` — keeps group header checkboxes in sync with card selection state
- `_undoStack` — up to 50 undo snapshots, Ctrl+Z pops them
- `localStorage` keys: `pbo_destinations_v1` (zones), `pbo_filter_sort_v1` (filter + sort)

---

## Component interaction diagram

```
Browser
  │
  │  GET /review  (Jinja2 render)
  │◄──────────────────── ui.py ◄── review.html template
  │
  │  GET /thumbnails?src=…
  │◄──────────────────── ui.py ──► thumbnails.py ──► ffmpeg (subprocess)
  │
  │  POST /api/scan
  │──────────────────► scan.py ──► BackgroundTask
  │                                   └─ scanner.py
  │                                       ├─ metadata.py
  │                                       └─ database.py
  │  GET /api/scan/status  (HTMX poll)
  │◄──────────────────── scan.py ← ScanProgress (module-level singleton)
  │
  │  GET /api/destinations/folder-children?root=photos&path=…
  │◄──────────────────── destinations.py (router) ──► destinations.py (module)
  │
  │  POST /api/move/dry-run
  │──────────────────► move.py (router) ──► mover.py ──► duplicates.py
  │
  │  POST /api/move/execute
  │──────────────────► move.py (router) ──► mover.py
  │                                           ├─ duplicates.py
  │                                           ├─ database.py  (mark_processed)
  │                                           └─ write_log_entry → SQLite
  │
  │  GET /api/move/log/rows  (HTMX poll)
  │◄──────────────────── move.py (router) ──► SQLite audit log
```

---

## Data flow: scan → review → move

```
1. SCAN
   Backup folders (/backups/device-n/YYYY-MM-DD/*.jpg|mp4)
        │
        ▼
   scanner.py  filters out is_processed() files
        │
        ▼
   ScanResult  (MediaFile list grouped by device + date)
        │
        ▼
   review.html  renders media grid via Jinja2

2. REVIEW  (browser-side JS state)
   User selects cards → drags / presses 1–9 → assigns to dest zone
   _applyAssignments()  builds  { src, photo_dest, video_dest }  assignment map

3. DRY-RUN
   POST /api/move/dry-run  →  mover.dry_run_batch()
        │
        ▼
   Per-file action table  (move / skip_duplicate / skip / error)  shown inline

4. EXECUTE
   POST /api/move/execute  →  mover.execute_batch()
        │
        ├─ destinations.ensure_folder_path()   (lazy create)
        ├─ shutil.copy2(src, dest)
        ├─ os.remove(src)
        ├─ database.mark_processed()
        └─ write_log_entry()  →  SQLite  →  /log page
```

---

## Docker image

```dockerfile
# Two-stage build
Builder  python:3.12-slim-bookworm
  └─ pip install dependencies into /venv

Runtime  python:3.12-slim-bookworm
  ├─ apt-get install ffmpeg
  ├─ copy /venv from builder
  └─ CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Bind mounts expected at runtime:

| Host path | Container path | Purpose |
|---|---|---|
| `./config` | `/config` | `config.yaml` |
| `/volume1/backup` | `/backups` | Per-device backup source folders |
| `/volume1/photo` | `/photos` | Photos library root |
| `/volume1/video` | `/videos` | Videos library root |
| `/volume1/logs` | `/logs` | Audit log file (optional) |
| `/volume1/cache` | `/cache` | SQLite DB + thumbnail cache |

---

## Security controls

| Concern | Mechanism |
|---|---|
| Path traversal | All user-supplied paths `.resolve()`d and checked to start with library root |
| XSS | `escHtml()` in JS; Jinja2 auto-escaping in templates |
| Authentication | Optional HTTP Basic Auth middleware (`app/main.py`); credentials in `config.yaml` |
| Injection | No shell=True subprocess calls; ffmpeg/ffprobe invoked with an explicit argument list |

---

## Key design decisions

| Decision | Rationale |
|---|---|
| ffmpeg only (no Pillow) | Removes native-library compilation pain on ARM64 NAS hardware |
| Native-codec fast path | Avoids transcoding delay for the common H.264 case |
| Lazy folder creation | Library stays clean even when moves are cancelled mid-batch |
| Single assignment engine | `_applyAssignments()` ensures undo, counts, and last-used zone are always consistent |
| Cooperative scan cancellation | Simple flag checked between files; no threads or OS signals needed |
| aiosqlite | Async-safe; persists processed-file state and GPS cache across container restarts |
| HTMX + Jinja2 (no JS build) | Zero build toolchain; lightweight; easy to maintain on a NAS |
