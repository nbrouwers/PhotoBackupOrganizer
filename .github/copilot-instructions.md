# Copilot Workspace Instructions – Photo Backup Organizer

## Project overview

Python/FastAPI web application that runs in Docker on a Synology NAS. It lets users review
phone-backup media and move files into a curated library via a drag-and-drop HTMX + Jinja2 UI.
All logic is in `app/`; templates in `app/templates/`; tests in `tests/`.

**Tech stack:** Python 3.12, FastAPI, Uvicorn, HTMX, Jinja2, aiosqlite, ffmpeg (thumbnails).  
**No Pillow** — all thumbnail and preview work uses ffmpeg subprocess calls only.  
**No JS build pipeline** — vanilla JS inside `<script>` blocks in Jinja2 templates.

---

## Mandatory workflow — follow this for EVERY change

1. **Read before editing** — always read the relevant file(s) before making changes.
2. **Run tests** after every code change:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/ -q
   ```
   All 48 tests must pass. Fix any failures before proceeding.
3. **Update documentation** — after any feature addition or behaviour change, update all three:
   - `README.md` — Features section, How it works, Using the application, REST API table
   - `requirements.md` — add or update the relevant FR/NFR; add a `†` footnote if it's new
   - `implementation-plan.md` — update the affected Phase and Key Decisions
4. **Commit and push** after every completed feature or fix:
   ```powershell
   git add <changed files>
   git commit -m "<type>: <short description>"
   git push origin main
   ```
   Commit message types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

---

## Coding conventions

### Python
- Use `from __future__ import annotations` at the top of every module.
- Type-annotate all function signatures.
- Path traversal protection: always `.resolve()` user-supplied paths and assert they start
  with the resolved library root before any filesystem operation.
- Never create destination folders speculatively — only at the moment a file is moved into them.
- Public helpers in `app/destinations.py` for all library path operations; routers must not
  construct raw paths themselves.

### FastAPI / routers
- Validate all request bodies with Pydantic models.
- Return `HTTPException(status_code=400, ...)` for bad input; 422 for missing required fields.
- HTML fragment endpoints (used by HTMX) use `response_class=HTMLResponse`.

### JavaScript (review.html)
- State lives in module-level `let` variables at the top of the `<script>` block.
- DOM mutations go through dedicated helper functions (`updateZoneCount`, `addDestZone`, etc.).
- Never embed raw JSON in `onclick="..."` attributes — use `data-*` attributes instead and
  read them with `this.dataset.*` in the handler.
- Use `CSS.escape()` when constructing CSS selectors from dynamic strings.

### Security
- Sanitise all user-supplied strings rendered into HTML with `escHtml()`.
- All file-path parameters from the API are resolved and checked against the library root.
- Never log or expose raw filesystem paths in user-visible error messages beyond what is needed.

---

## File layout (key files)

```
app/
  config.py          – YAML config loader, get_config() singleton
  database.py        – aiosqlite helpers (mark_processed, is_processed)
  scanner.py         – backup folder scanner, two-phase progress
  metadata.py        – EXIF / ffprobe capture-date and GPS extraction
  thumbnails.py      – ffmpeg thumbnail + H.264 preview generation
  destinations.py    – library path helpers (tree listing, folder creation, file counts)
  duplicates.py      – SHA-256 duplicate detection
  mover.py           – dry_run_batch, execute_batch, write_log_entry
  routers/
    scan.py           – /api/scan/*
    destinations.py   – /api/destinations/*
    move.py           – /api/move/*
    ui.py             – HTML pages, /thumbnails, /video-preview, /media, /api/geocode
  templates/
    base.html         – shared layout, nav, CSS variables
    index.html        – scan page
    review.html       – drag-and-drop review page (FolderPicker, lightbox, zone badges)
    log.html          – audit log page
tests/
  conftest.py         – shared fixtures (tmp_path config, library dirs)
  test_config.py
  test_destinations.py
  test_duplicates.py
  test_metadata.py
  test_mover.py
```

---

## REST API — endpoints currently implemented

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/scan` | Trigger background scan |
| `GET`  | `/api/scan/status` | Poll scan progress |
| `GET`  | `/api/scan/result` | Last scan result |
| `GET`  | `/api/scan/folders` | Scannable sub-folders per device |
| `GET`  | `/api/geocode` | Reverse-geocode GPS (`?lat=&lon=`) |
| `GET`  | `/api/destinations/folder-children` | Lazy-load tree children (`?root=&path=`) |
| `GET`  | `/api/destinations/folder-count` | Existing file count at a path (`?root=&path=`) |
| `POST` | `/api/destinations/ensure-folder` | Create folder at relative path (`{root, name}`) |
| `POST` | `/api/move/dry-run` | Simulate batch move |
| `POST` | `/api/move/execute` | Execute batch move |
| `POST` | `/api/move/delete` | Delete source files (`{paths: [...]}`) |
| `GET`  | `/api/move/log` | Audit log (JSON) |
| `GET`  | `/api/move/log/rows` | Audit log rows (HTML, HTMX) |
| `GET`  | `/thumbnails` | Serve thumbnail (`?src=`) |
| `GET`  | `/health` | Health check |
