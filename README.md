# Photo Backup Organizer

A Python web application that runs in a Docker container on a Synology NAS. It streamlines the process of moving photos and videos from per-device automatic backup folders into a curated, centrally organised library — separated by media type, and filed into either per-event folders or quarterly catch-all folders.

---

## Table of Contents

1. [How it works](#how-it-works)
2. [Project structure](#project-structure)
3. [Development setup](#development-setup)
4. [Running tests](#running-tests)
5. [Building &amp; publishing the Docker image (GitHub Actions CI/CD)](#building-the-docker-image)
6. [Deploying to a Synology NAS](#deploying-to-a-synology-nas)
7. [Configuration reference](#configuration-reference)
8. [Using the application](#using-the-application)

---

## How it works

```
Android phone  ──►  Synology backup folder  ──►  Photo Backup Organizer  ──►  Central library
                     /backups/alice/                 (web UI review)             /photos/
                     /backups/bob/                                                /videos/
```

1. Your phone's backup app (e.g. Synology Photos, FolderSync) continuously syncs new media to a dedicated per-device folder on the NAS.
2. You open the Photo Backup Organizer web UI and press **Scan** to discover all unprocessed files.
3. Files are grouped by device and capture date. You assign each group (or individual file) to a destination:
   - An **event folder** (e.g. `/photos/holidays/2026 Amsterdam/`)
   - The automatic **quarterly folder** (e.g. `/photos/2026/Q1/`)
4. Press **Preview changes (dry-run)** to see exactly what will happen — no files are moved yet.
5. Review the dry-run table and press **Confirm & Move** to execute. Files are copied to the destination, then deleted from the source only after a successful write.
6. Already-processed files are remembered in an SQLite database and never re-presented to you.

---

## Project structure

```
photo-backup-organizer/
├── app/
│   ├── main.py            # FastAPI application factory and entry point
│   ├── config.py          # YAML config loader + Pydantic validation
│   ├── database.py        # Async SQLite persistence (aiosqlite)
│   ├── scanner.py         # Backup folder scanner
│   ├── metadata.py        # EXIF / ffprobe capture-date extraction
│   ├── thumbnails.py      # Pillow photo thumbnails + ffmpeg video posters
│   ├── destinations.py    # Library path resolution (quarterly / event)
│   ├── duplicates.py      # SHA-256-based duplicate detection
│   ├── mover.py           # Dry-run and execute batch move logic
│   ├── routers/
│   │   ├── scan.py        # GET/POST /api/scan
│   │   ├── destinations.py# /api/destinations
│   │   ├── move.py        # POST /api/move/dry-run  POST /api/move/execute
│   │   └── ui.py          # HTML page routes (Jinja2)
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

Synology NAS models use different CPU architectures; the pipeline builds for all of them at once:

| Architecture | Synology models |
|---|---|
| `linux/amd64` | Intel/AMD models (DS220+, DS420+, DS720+, DS920+, DS923+, …) |
| `linux/arm64` | ARM64 models (DS223j, DS423j — Realtek RTD1619B) |
| `linux/arm/v7` | Older ARMv7 value-line models |

The NAS automatically selects the correct variant when it pulls the image.

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
│  pytest     │                    │  QEMU + Docker Buildx    │
│  (Python    │                    │  → linux/amd64           │
│   3.12)     │                    │  → linux/arm64           │
│             │                    │  → linux/arm/v7          │
└─────────────┘                    │  → push to registry      │
                                   └──────────────────────────┘
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

The first build takes approximately 10–15 minutes (QEMU cross-compilation is slower than native). Subsequent builds take 3–5 minutes thanks to the layer cache.

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

### Building locally (requires Docker Desktop)

If you later install Docker Desktop on your machine, use the included PowerShell script for local builds:

```powershell
# Build and run locally (amd64 only)
.\build.ps1 -LoadAmd64

# Build all platforms and push to Docker Hub
.\build.ps1 -Registry your-dockerhub-username -Push

# Export OCI tarballs for offline NAS deployment
.\build.ps1 -ExportOci
```

---

## Deploying to a Synology NAS

### Prerequisites on the NAS

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

Edit the volume paths in `docker-compose.yml` to match your NAS volume layout if they differ from the defaults.

### 4a. Deploy with docker compose (SSH)

```bash
ssh user@<NAS_IP>
cd /volume1/docker/photo-backup-organizer

# Pull from registry
docker compose pull

# Start in the background
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

Open `http://<NAS_IP>:8000` in a browser on your local network.

### Workflow

#### Step 1 – Scan

Press **Scan now**. The application scans all configured backup folders in the background. Progress is updated live. Files already moved in a previous session are automatically skipped.

#### Step 2 – Review

The **Review** page shows all unprocessed files grouped by device and capture date.

For each group, choose a destination from the **Destination for this group** dropdown:

| Option | Result |
|---|---|
| **Quarterly folder (auto)** | Files go to `<library_root>/<year>/Q<quarter>/` based on their capture date |
| **Event folder** | Pick an existing category + event, or type a new event name to create it on the spot |

You can also expand individual file rows and set a per-file destination override.

#### Step 3 – Preview changes (dry-run)

Click **Preview changes (dry-run)**. No files are moved. A summary table shows:

| Badge | Meaning |
|---|---|
| 🟢 move | File will be moved as-is |
| 🟡 rename | A non-duplicate filename collision exists; a numeric suffix (`_1`, `_2`, …) will be appended |
| 🔴 skip (duplicate) | An identical file (same size + SHA-256) already exists at the destination |
| ❌ error | Something unexpected would prevent the move |

#### Step 4 – Confirm & Move

If the dry-run looks correct, press **Confirm & Move** to execute. Each file is:

1. Copied to the destination using `shutil.copy2` (preserving timestamps and metadata).
2. Deleted from the source **only after** the copy completes successfully.

#### Step 5 – Log

The **Log** page shows the outcome of the last batch (counts + per-file detail).  
A persistent audit log is also written to `/logs/photo-backup-organizer.log` on the host:

```
2026-03-23T10:15:42+00:00	move	/backups/alice/2026-03-20/IMG_1234.jpg	/photos/2026/Q1/IMG_1234.jpg
2026-03-23T10:15:43+00:00	skip_duplicate	/backups/bob/2026-03-20/VID_0001.mp4	/videos/2026/Q1/VID_0001.mp4
```

### REST API

The application also exposes a JSON API (documented at `http://<NAS_IP>:8000/docs`):

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/scan` | Trigger a background scan |
| `GET` | `/api/scan/status` | Poll scan progress |
| `GET` | `/api/scan/result` | Retrieve last scan result |
| `GET` | `/api/destinations/categories` | List event categories |
| `GET` | `/api/destinations/events` | List event folders in a category |
| `POST` | `/api/destinations/events` | Create a new event folder |
| `GET` | `/api/destinations/quarterly` | Resolve a quarterly path |
| `POST` | `/api/move/dry-run` | Simulate a batch move |
| `POST` | `/api/move/execute` | Execute a batch move |
| `GET` | `/api/move/log` | Recent audit log entries |
| `GET` | `/thumbnails` | Serve a thumbnail (`?src=<path>`) |
| `GET` | `/health` | Health check |
