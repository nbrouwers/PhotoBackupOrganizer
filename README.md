# Photo Backup Organizer

A Python web application that runs in a Docker container on a Synology NAS. It streamlines the process of moving photos and videos from per-device automatic backup folders into a curated, centrally organised library — separated by media type and filed into destination folders that you define.

---

## Table of Contents

1. [Features](#features)
2. [How it works](#how-it-works)
3. [Project structure](#project-structure)
4. [Development setup](#development-setup)
5. [Running tests](#running-tests)
6. [Building &amp; publishing the Docker image (GitHub Actions CI/CD)](#building-the-docker-image)
7. [Deploying to a Synology NAS](#deploying-to-a-synology-nas)
8. [Configuration reference](#configuration-reference)
9. [Using the application](#using-the-application)

---

## Features

### Scan
- **Selective folder scanning** — expand "Choose folders to scan" to cherry-pick individual sub-folders per device. Uncheck any you want to skip; the rest are scanned normally.
- **Quarter & date presets** — one-click quarter buttons (current quarter plus the last four) narrow the scan to files modified in that period, drastically reducing scan time on large backup folders. Free-form From/To date fields are also available.
- **Two-phase progress bar** — the scanner first counts all candidate files, then processes them one by one. A live progress bar (percentage, current filename, found count) updates every 2 seconds via HTMX polling — no full-page refresh.- **Cancel scan** — a ✕ Cancel button appears inside the live progress panel while a scan is running. Clicking it sets a cancellation flag that the scanner checks between files; the scan stops cleanly after the current file without restarting the server.
- **Per-device file counts** — the completed-scan banner shows how many new files were found per device (e.g. “Alice’s Phone: 47 | Bob’s Phone: 12”), making it immediately clear whether a device actually synced anything new.- **Detailed logging** — every file examined is logged at DEBUG level; per-device summaries at INFO level.
- **Automatic skip of processed files** — an SQLite database records every moved file so it is never re-presented on a subsequent scan.

### Review
- **Tree-based destination picker** — navigate the photos/videos library as a lazy-loading folder tree. Expand any folder to see its children, create new sub-folders inline at any depth (even immediately inside a just-created folder), and select any folder in the tree as a destination. The relative path from the library root is shown as the zone label.
- **Destination file counts** — each destination zone badge shows how many photos (📸) and videos (🏅) already exist in that folder, plus how many are staged to be moved there (e.g. `📸 47+3  🏅 12+1`).
- **Source filter** — filter the grid to show only files from a specific device via the dropdown in the top bar.
- **Sort** — sort visible cards by date ascending, date descending, or location A–Z.
- **Sticky top bar** — the Delete, Dry-run, and Move buttons stay pinned at the top of the screen while scrolling the media grid, so they are always accessible.
- **Drag-and-drop assignment** — drag one or more file cards onto a destination zone. Multi-select with Shift+Click or Ctrl+Click before dragging. Photos route to the photos library path; videos route to the videos library path automatically.
- **Keyboard zone shortcuts** — press `1`–`9` to instantly assign the selected card(s) to destination zone 1–9 (the zone number is shown in the badge). No dragging required; combine with group select to file a whole day's photos in two keystrokes.
- **Date-group select all** — every device · date group header has a **Select all** button that selects every visible card in that group in one click.
- **Undo last assignment** — press `Ctrl+Z` (or `Cmd+Z`) to detach the most-recently-assigned batch from its zone and restore each card to its previous state (or unassigned). Up to 50 operations are tracked. Badge unassign clicks are also undoable.
- **Quick-assign to last-used zone** — once you have assigned at least one file, a **▷ Zone name** button appears in the top bar. Click it (or press `Q`) to assign all selected cards to the same destination without using the mouse at all.
- **Delete selected** — select one or more cards and click 🗑 Delete to permanently remove the source files from the backup folder. A confirmation dialog is shown before any file is deleted.
- **Video play icon** — video thumbnails are decorated with a `▶` overlay badge so they are instantly distinguishable from photos.
- **Instant video preview for H.264/VP8/VP9/AV1 files** — clicking a video card opens it in the lightbox immediately with no transcoding wait. ffprobe checks the container codec; browser-native videos are streamed directly from the source. Only HEVC/H.265 files are transcoded to H.264 on first open (cached afterwards).
- **GPS location labels** — if a photo's EXIF data contains GPS coordinates, the card shows a `⊙ City, Country` label (e.g. `⊙ Amsterdam, Netherlands`). Locations are reverse-geocoded via OpenStreetMap Nominatim, cached permanently in SQLite, and appear in the full-screen lightbox caption.
- **Full-screen lightbox** — double-click any card to preview the full-resolution photo or play the video inline. Use ‹ / › arrow buttons or ← / → keyboard keys to navigate between visible cards without closing the lightbox. A 🗑 delete button in the lightbox toolbar deletes the currently open file, then automatically advances to the next one.
- **Tile-size slider** — resize the grid from 2 to 10 columns.

### Move
- **Dry-run preview** — see exactly what will happen (move / skip duplicate / error) before any file is touched.
- **Duplicate detection** — identical files (same size + SHA-256 hash) at the destination are skipped automatically.
- **Same-filename skip** — if a file with the same name already exists at the destination (but is not a byte-for-byte duplicate), the move is skipped to prevent accidental overwriting. The user can delete or rename the source file and retry.
- **Safe copy-then-delete** — files are written to the destination first; the source is deleted only after a successful write.
- **Lazy folder creation** — destination folders are only created on the filesystem at the moment a file is actually moved into them. No empty folders are ever created speculatively, even when a video destination is mirrored from a photo destination.
- **Progress bar** — the Confirm & Move button shows an animated progress bar with a file count summary while the execute request is in flight.

### Infrastructure
- **No Docker required on your desktop** — the GitHub Actions CI/CD pipeline builds and publishes the `linux/amd64` image on every push to `main`.
- **Optional HTTP Basic Auth** — protect the web UI with a username and password in `config.yaml`.
- **Persistent cache** — thumbnails and GPS lookups survive container restarts via the `/cache` bind-mount volume.

---

## How it works

```
Android phone  ──►  Synology backup folder  ──►  Photo Backup Organizer  ──►  Central library
                     /backups/alice/                 (web UI review)             /photos/
                     /backups/bob/                                                /videos/
```

1. Your phone's backup app (e.g. Synology Photos, FolderSync) continuously syncs new media to a dedicated per-device folder on the NAS.
2. You open the Photo Backup Organizer web UI and press **Scan** to discover all unprocessed files.
3. Files are grouped by device and capture date. Add one or more destination folders in the right-hand panel by navigating the library folder tree and selecting a folder (or creating a new one inline at any nesting level):
   - A folder you navigate to in the photos/videos library tree
   - A brand-new folder you create inline (created on the server only when a file is actually moved into it)
4. Press **Preview changes (dry-run)** to see exactly what will happen — no files are moved yet.
5. Review the dry-run table and press **Confirm & Move** to execute. A progress bar shows the move in flight. Files are copied to the destination, then deleted from the source only after a successful write.
6. Already-processed files are remembered in an SQLite database and never re-presented to you.

---

## Project structure

```
photo-backup-organizer/
├── app/
│   ├── main.py            # FastAPI application factory and entry point
│   ├── config.py          # YAML config loader + Pydantic validation
│   ├── database.py        # Async SQLite persistence (aiosqlite)
│   ├── scanner.py         # Backup folder scanner with two-phase progress
│   ├── metadata.py        # EXIF / ffprobe capture-date and GPS extraction
│   ├── geocoder.py        # Reverse geocoding via Nominatim (OpenStreetMap)
│   ├── thumbnails.py      # ffmpeg-only thumbnails; codec probe skips transcode for H.264/VP9/AV1
│   ├── destinations.py    # Library path helpers (child-folder listing, folder creation)
│   ├── duplicates.py      # SHA-256-based duplicate detection
│   ├── mover.py           # Dry-run and execute batch move logic
│   ├── routers/
│   │   ├── scan.py        # GET/POST /api/scan  GET /api/scan/folders
│   │   ├── destinations.py# /api/destinations
│   │   ├── move.py        # POST /api/move/dry-run  POST /api/move/execute  POST /api/move/delete
│   │   └── ui.py          # HTML page routes (Jinja2) + /api/geocode
│   └── templates/         # HTMX + Jinja2 HTML templates
├── tests/                 # pytest test suite
├── config/
│   └── config.example.yaml
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.md
└── implementation-plan.md
```

---

## Development setup

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.9 + | 3.12 recommended; 3.9 works |
| pip | any | bundled with Python |
| ffmpeg | any recent | Required at runtime for video thumbnails; optional for tests |

> **Windows note:** `ffmpeg` is only needed to generate video poster frames. All unit tests run without it.

### 1. Clone the repository

```bash
git clone https://github.com/your-org/photo-backup-organizer.git
cd photo-backup-organizer
```

### 2. Create and activate a virtual environment

```bash
# Create
python -m venv .venv

# Activate – Windows PowerShell
.venv\Scripts\Activate.ps1

# Activate – macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -e ".[dev]"
```

This installs the application in editable mode together with all runtime and development dependencies (FastAPI, Pillow, aiosqlite, pytest, etc.).

### 4. Create a local config file

```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` and point `devices`, `library.photos_root`, and `library.videos_root` at directories that exist on your local machine for testing.

### 5. Run the development server

```bash
PHOTO_BACKUP_CONFIG=config/config.yaml uvicorn app.main:app --reload
```

On Windows PowerShell:

```powershell
$env:PHOTO_BACKUP_CONFIG = "config\config.yaml"
uvicorn app.main:app --reload
```

The UI is available at `http://localhost:8000`.

---

## Running tests

```bash
pytest tests/ -v
```

The test suite uses `tmp_path` fixtures to create isolated temporary directories — no real NAS paths or media files are required.

To also run the EXIF extraction test, install the optional `piexif` package first:

```bash
pip install piexif
pytest tests/ -v
```

**Expected output:** 48 passed, 0 skipped.

---

## Building the Docker image

The repository includes a GitHub Actions CI/CD pipeline (`.github/workflows/docker-publish.yml`) that **automatically builds and publishes the Docker image every time you push to `main`** — no Docker installation required on your own machine.

The image targets **`linux/amd64`** — the platform of the Intel Celeron J4025 (and all other Intel/AMD 64-bit Synology NAS models).

---

### How the pipeline works

The workflow runs two jobs in sequence:

```
push to main
      │
      ▼
┌─────────────┐   all tests pass   ┌──────────────────────────┐
│  Job 1:     │ ─────────────────► │  Job 2:                  │
│  test       │                    │  build                   │
│             │                    │                          │
│  pytest     │                    │  Docker Buildx           │
│  (Python    │                    │  → linux/amd64           │
│   3.12)     │                    │  → push to registry      │
└─────────────┘                    └──────────────────────────┘
```

- **If tests fail**, the build job is cancelled and no image is published.
- **Pull requests** trigger the test and build jobs but do not push the image.
- **Layer caching** is enabled so subsequent builds only recompile what changed.

---

### Step 1 — Push the repository to GitHub

Create a new repository on GitHub and push:

```bash
git remote add origin https://github.com/your-username/photo-backup-organizer.git
git push -u origin main
```

The Actions workflow file is already committed and will be picked up immediately.

---

### Step 2 — Watch the first run

1. Open your repository on GitHub.
2. Click the **Actions** tab.
3. You will see a workflow run called **"CI — Test, Build & Publish"** in progress.
4. Click it to see the two jobs: **Run tests** and **Build & publish Docker image**.

The first build takes approximately 3–5 minutes. Subsequent builds are faster thanks to the layer cache.

---

### Step 3 — Find your published image

Once the workflow completes successfully, the image is published to **GitHub Container Registry (GHCR)** — automatically, with no extra credentials needed:

```
ghcr.io/your-username/photo-backup-organizer:latest
```

To browse it: open your GitHub repository → **Packages** (right-hand sidebar).

**Images are tagged automatically:**

| Tag | When it's created |
|---|---|
| `latest` | Every push to `main` |
| `main` | Every push to the `main` branch |
| `sha-<7chars>` | Every push (points at that exact commit) |
| `v1.2` / `1.2.3` | When you push a Git tag like `v1.2.3` |

---

### Step 4 (optional) — Also push to Docker Hub

GHCR is private by default (accessible with a GitHub token). If you want a **public image** anyone can pull without authentication, add Docker Hub as a second registry.

**a) Create a Docker Hub access token**

1. Sign up at **https://hub.docker.com** (free).
2. Click your avatar → **Account Settings → Security → New Access Token**.
3. Give it a description (e.g. `github-actions`) and click **Generate**.
4. Copy the token — it is only shown once.

**b) Add secrets to your GitHub repository**

1. Open your repository on GitHub.
2. Go to **Settings → Secrets and variables → Actions**.
3. Click **New repository secret** twice:

| Secret name | Value |
|---|---|
| `DOCKERHUB_USERNAME` | Your Docker Hub username |
| `DOCKERHUB_TOKEN` | The access token you just generated |

Once both secrets are present, the next push to `main` will automatically log in to Docker Hub and publish the image there as well:

```
your-dockerhub-username/photo-backup-organizer:latest
```

No changes to the workflow file are needed — the pipeline detects the secrets automatically.

---

## Deploying to a Synology NAS

### Prerequisites on the NAS

- DSM 7.x
- **Container Manager** installed (from the Package Center)
- SSH access enabled (optional, but recommended for `docker compose`)

### 1. Prepare the folder structure on the NAS

Create the directories that will be bind-mounted into the container. Adjust `/volume1` to match your actual NAS volume:

```
/volume1/backups/alice/          ← Alice's phone backup root
/volume1/backups/bob/            ← Bob's phone backup root
/volume1/photos/                 ← Central photo library
/volume1/videos/                 ← Central video library
/volume1/logs/photo-backup-organizer/
/volume1/docker/photo-backup-organizer/config/
```

```bash
mkdir -p /volume1/backups/alice
mkdir -p /volume1/backups/bob
mkdir -p /volume1/photos
mkdir -p /volume1/videos
mkdir -p /volume1/logs/photo-backup-organizer
mkdir -p /volume1/docker/photo-backup-organizer/config
```

### 2. Create the configuration file

```bash
cp config/config.example.yaml /volume1/docker/photo-backup-organizer/config/config.yaml
```

Then edit `/volume1/docker/photo-backup-organizer/config/config.yaml` on the NAS and set the correct paths and device labels.

### 3. Copy docker-compose.yml to the NAS

```bash
scp docker-compose.yml user@<NAS_IP>:/volume1/docker/photo-backup-organizer/
```

### 4a. Deploy with docker compose (SSH)

```bash
ssh user@<NAS_IP>
cd /volume1/docker/photo-backup-organizer

# Pull the image from Docker Hub and start
docker compose pull
docker compose up -d
```

### 4b. Deploy via Container Manager UI

1. Open **Container Manager** in DSM.
2. Go to **Project → Create**.
3. Set the project path to `/volume1/docker/photo-backup-organizer/`.
4. DSM reads `docker-compose.yml` from that folder automatically.
5. Click **Next**, review the compose settings, and click **Done** to deploy.

### 5. Verify the container is running

```bash
docker ps --filter name=photo-backup-organizer
docker logs photo-backup-organizer
```

The log should show:

```
INFO     app.main: Photo Backup Organizer starting up
INFO     app.main: Config loaded: 2 device(s), photos_root=/photos, videos_root=/videos
INFO     uvicorn.server: Application startup complete.
```

---

## Configuration reference

All configuration lives in a single YAML file (default: `/config/config.yaml` inside the container, mapped from the host via the bind mount defined in `docker-compose.yml`).

```yaml
# One entry per backup device
devices:
  - label: "Alice's Phone"    # Display name shown in the UI
    path: /backups/alice      # Path as seen inside the container

  - label: "Bob's Phone"
    path: /backups/bob

# Central library roots (inside the container)
library:
  photos_root: /photos
  videos_root: /videos

# Supported extensions (case-insensitive; defaults shown)
extensions:
  photos: [.jpg, .jpeg, .png, .heic, .heif, .dng, .raw, .arw, .nef, .cr2, .cr3, .webp]
  videos: [.mp4, .mov, .m4v, .mkv, .avi, .3gp, .webm]

# Web server port (also set the port mapping in docker-compose.yml)
server:
  port: 8000

# Thumbnail cache settings
cache:
  path: /cache
  thumb_size: 300   # Max thumbnail dimension in pixels

# Optional: protect the UI with HTTP Basic Auth
# security:
#   basic_auth:
#     username: admin
#     password: changeme
```

A configuration change requires a container restart:

```bash
docker compose restart
```

---

## Using the application

Open `http://<NAS_IP>:9121` in a browser on your local network.

### Workflow

#### Step 1 – Scan

1. Optionally expand **Choose folders to scan** and uncheck sub-folders you want to skip.
2. Optionally click a **quarter preset** (e.g. `Q1 2026`) or fill in the From/To date fields to limit the scan to a specific period. Scanning one quarter instead of all years takes a fraction of the time.
3. Press **Scan now**. The scanner runs in the background and updates the progress bar every 2 seconds.
4. When the scan completes, click **Go to Review**.

#### Step 2 – Review

The **Review** page shows all unprocessed files as a draggable tile grid.

**Destinations panel (right column)**

1. In the **Photo destination** tree, expand folders to navigate the library. Click any folder to select it as the destination — the relative path (e.g. `2026/Holidays`) is shown as the zone label.
2. To create a new folder, use the **＋** input that appears at the bottom of each expanded folder. You can immediately create subfolders inside a newly created folder.
3. By default the same relative path is used in the videos library (**Same folder in videos library** checkbox). Uncheck it to navigate an independent video path.
4. Click **+ Add destination** to add the zone to your panel. Destinations are saved in the browser (`localStorage`) and persist across page reloads.
5. Use the **×** button on any zone to remove it; files on disk are not affected.
6. Each zone badge shows the current file counts: `📸 47  🏅 12` for existing content, or `📸 47+3  🏅 12+1` when files are staged.

- **Source filter** dropdown — show only files from one device.
- **Sort** dropdown — order cards by date ascending, date descending, or location A–Z.
- Click a card to select it (Shift+Click for range, Ctrl/Cmd+Click to toggle).
- **Delete selected** (🗑 button, top-right) — permanently deletes the selected source files after a confirmation prompt. Use this to remove unwanted duplicates or junk before moving.
- Drag one or more selected cards onto a destination zone to assign them. Photos go to the photos path; videos go to the videos path.
- Double-click a card to open it full-screen. Use the **‹ / ›** arrows or ← / → keyboard keys to navigate without closing the lightbox. Press the **🗑** button in the lightbox toolbar to delete the currently open file; the lightbox automatically advances to the next file.
- Cards with GPS data show a `⊙ City, Country` label; the location also appears in the lightbox caption.
- Use the **Grid size** slider to change the number of columns (2–10).
- The top bar with the Delete, Dry-run, and Move buttons stays pinned at the top of the screen while scrolling.

#### Step 3 – Preview changes (dry-run)

Click **Preview changes (dry-run)**. No files are moved. A summary table shows:

| Badge | Meaning |
|---|---|
| 🟢 move | File will be moved as-is |
| � skip (duplicate) | An identical file (same size + SHA-256) already exists at the destination |
| 🔴 skip | A file with the same name already exists at the destination (not a duplicate) — move is skipped to prevent overwriting |
| ❌ error | Something unexpected would prevent the move |

#### Step 4 – Confirm & Move

If the dry-run looks correct, press **Confirm & Move** to execute. An animated progress bar is shown while the operation runs. Each file is:

1. Copied to the destination using `shutil.copy2` (preserving timestamps and metadata). The destination folder is created at this point if it does not already exist.
2. Deleted from the source **only after** the copy completes successfully.

#### Step 5 – Log

The **Log** page shows the outcome of the last batch (counts + per-file detail).  
A persistent audit log is also written to `/logs/photo-backup-organizer.log` on the host:

```
2026-03-23T10:15:42+00:00	move	/backups/alice/2026-03-20/IMG_1234.jpg	/photos/2026/Q1/IMG_1234.jpg
2026-03-23T10:15:43+00:00	skip_duplicate	/backups/bob/2026-03-20/VID_0001.mp4	/videos/2026/Q1/VID_0001.mp4
```

### REST API

The application also exposes a JSON API (documented at `http://<NAS_IP>:9121/docs`):

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/scan` | Trigger a scan (optional body: `include_paths`, `date_from`, `date_to`) |
| `GET` | `/api/scan/status` | Poll scan progress (includes `cancelled`, `device_counts`) |
| `POST` | `/api/scan/cancel` | Request cancellation of the running scan |
| `GET` | `/api/scan/result` | Retrieve last scan result |
| `GET` | `/api/scan/folders` | List scannable sub-folders per device |
| `GET` | `/api/geocode` | Reverse-geocode GPS coords (`?lat=&lon=`) |
| `GET` | `/api/destinations/folder-children` | List immediate sub-folders at any depth in the library tree (`?root=photos\|videos&path=rel/path`) |
| `GET` | `/api/destinations/folder-count` | Count existing files at a library path (`?root=photos\|videos&path=rel/path`) |
| `POST` | `/api/destinations/ensure-folder` | Create a folder at an arbitrary relative path — supports nesting with `/` (body: `{root, name}`) |
| `GET` | `/api/move/log/rows` | Recent audit log as HTML rows (used by HTMX log page) |
| `GET` | `/api/destinations/categories` | List event categories (legacy) |
| `GET` | `/api/destinations/events` | List event folders in a category (legacy) |
| `POST` | `/api/destinations/events` | Create a new event folder (legacy) |
| `POST` | `/api/move/dry-run` | Simulate a batch move |
| `POST` | `/api/move/execute` | Execute a batch move |
| `POST` | `/api/move/delete` | Permanently delete source files by path (body: `{paths: [...]}`) |
| `GET` | `/api/move/log` | Recent audit log entries |
| `GET` | `/video-preview` | Serve a browser-compatible video preview (`?src=<path>`); 302 redirect for native codecs, H.264 transcode for HEVC |
| `GET` | `/thumbnails` | Serve a thumbnail (`?src=<path>`) |
| `GET` | `/health` | Health check |
