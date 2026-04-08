# Photo Backup Organizer – Requirements

## 1. Overview

A Python application running in a Docker container on a Synology NAS. It moves photos and videos from per-device backup folders into a centrally organized photo and video library, reducing the manual effort of sorting and filing media after automatic phone backups.

---

## 2. Definitions

| Term | Description |
|---|---|
| **Backup folder** | A device-specific source folder where an Android phone automatically deposits backed-up media, containing daily subfolders (e.g. `/backups/phone-alice/2026-03-20/`). |
| **Library** | The central, curated collection of media, split into a photos root (e.g. `/photos/`) and a videos root (e.g. `/videos/`). |
| **Event folder** | A named subfolder inside the library dedicated to a specific occasion (e.g. `/photos/holidays/2026 amsterdam/`). |
| **Quarterly folder** | A catch-all subfolder for media not assigned to any event, organized by year and quarter (e.g. `/photos/2026/Q1/`). |

---

## 3. Functional Requirements

### 3.1 Source Discovery

- **FR-01** The application shall scan all configured backup folders at startup and identify media files (photos and videos) that have not yet been processed.
- **FR-02** The application shall support multiple source devices, each with its own dedicated backup root folder.
- **FR-03** The application shall recurse into daily subfolders within each device backup folder.
- **FR-04** The application shall distinguish between photo file types (JPEG, PNG, HEIC, RAW variants, etc.) and video file types (MP4, MOV, MKV, AVI, etc.).

### 3.2 Destination Management

- **FR-05** The application shall maintain a configured photos library root and a separate videos library root.
- **FR-06** The application shall support two destination types:
  - **Event folder** – a named folder nested under a category inside the library (e.g. `/photos/holidays/2026 amsterdam/`).
  - **Quarterly folder** – an auto-generated folder based on the media's capture date, following the pattern `<library-root>/<year>/Q<quarter>/` (e.g. `/photos/2026/Q1/`).
- **FR-07** The application shall be able to create new event folders on demand, including any required intermediate category folders (e.g. `holidays/`, `birthdays/`).
- **FR-08** Quarterly folders shall be created automatically if they do not yet exist when files are moved into them.

### 3.3 File Processing

- **FR-09** The application shall move files from the backup location to the chosen destination (move, not copy, to avoid duplicate storage).
- **FR-10** The application shall read the capture date/time from file metadata (EXIF data for photos; container metadata for videos) with fallback to the file's last-modified date.
- **FR-11** The application shall detect duplicate files at the destination before moving and skip or flag them rather than overwriting existing files.
- **FR-12** The application shall preserve original filenames. When a filename collision exists that is not a duplicate, it shall append a numeric suffix to avoid overwriting (e.g. `IMG_1234_1.jpg`).
- **FR-13** The application shall log every file operation (moved, skipped, or error) with source path, destination path, and reason.

### 3.4 User Workflow

- **FR-14** The application shall provide a web-based user interface accessible from within the local network (no public internet exposure required).
- **FR-15** The UI shall present unprocessed media grouped by source device and capture date, allowing the user to review them before any files are moved.
- **FR-16** The UI shall allow the user to assign a group of files (e.g. all files from a specific date range) to either an event folder or the quarterly fallback.
- **FR-17** The UI shall allow the user to select individual files and override the group assignment for them.
- **FR-18** The UI shall allow the user to browse and select existing event folders as a destination, or create a new event folder inline.
- **FR-19** The UI shall display a thumbnail preview for photos and a poster-frame preview for videos.
- **FR-20** The UI shall provide a confirmation step before files are physically moved.
- **FR-21** The UI shall display a processing log after each batch move operation.

### 3.5 Configuration

- **FR-22** All configurable values shall be stored in a single configuration file (YAML or TOML) mounted into the container at a well-known path.
- **FR-23** The configuration shall support:
  - A list of backup source folders, each with a human-readable device label.
  - The photos library root path.
  - The videos library root path.
  - Supported photo and video file extensions (with sensible defaults).
  - The port on which the web UI is served.
- **FR-24** Configuration changes shall take effect on application restart without rebuilding the container image.

---

## 4. Non-Functional Requirements

- **NFR-01 Containerized** – The application shall be packaged as a Docker image and run via `docker-compose` on a Synology NAS (DSM 7.x, Container Manager).
- **NFR-02 No data loss** – Files shall never be deleted from the source until they have been confirmed as successfully written to the destination.
- **NFR-03 Idempotent scanning** – Re-scanning backup folders shall not re-present already-processed files to the user.
- **NFR-04 Performance** – Thumbnail generation and file scanning shall run asynchronously so the UI remains responsive during long operations.
- **NFR-05 Auditability** – A persistent log file (mounted from the host) shall record all move operations with timestamps, enabling recovery of accidental moves.
- **NFR-06 Security** – The web UI shall be restricted to the local network. Optional basic-auth password protection shall be configurable.
- **NFR-07 Resource constraints** – The container shall be usable on entry-level NAS hardware (e.g. 512 MB RAM limit, ARM or x86-64 CPU).
- **NFR-08 Maintainability** – The codebase shall follow standard Python project structure with dependency management via `requirements.txt` or `pyproject.toml`.

---

## 5. Out of Scope

- Automatic, unattended moving of files without user review.
- Cloud photo service integration (Google Photos, iCloud, etc.).
- Face recognition or AI-based photo categorization.
- Editing, transcoding, or compressing media files.
- Management of files already in the library (reorganization of existing library content).
- Mobile or native desktop UI – a web UI is sufficient.

---

## 6. Constraints and Assumptions

- Backup folders are mounted into the Docker container as read-write bind mounts (source folders need write access to allow files to be moved out).
- Library folders are mounted into the Docker container as read-write bind mounts.
- Android backup apps (e.g. Synology Photos, FolderSync) are already configured and running independently; this application only processes the resulting files.
- Capture date metadata is sufficiently reliable for quarterly folder assignment in the majority of cases.
- The NAS runs Docker / Container Manager with support for `docker-compose` v2.

---

## 7. Suggested Technology Stack

| Concern | Suggestion |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI (async, lightweight) |
| UI | HTMX + Jinja2 templates (no separate JS build step) |
| EXIF / metadata | `Pillow`, `exifread`, `ffprobe` (via subprocess) |
| Configuration | `PyYAML` or `tomllib` (stdlib in 3.11+) |
| Containerization | Multi-stage `Dockerfile`, `docker-compose.yml` |
| Logging | Python `logging` module, writes to mounted log file |
