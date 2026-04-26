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
- **FR-01c†** The application shall support filtering scans by date range, with preset quarter buttons that dynamically show only quarters containing media in the backup locations.
- **FR-02** The application shall support multiple source devices, each with its own dedicated backup root folder.
- **FR-03** The application shall recurse into daily subfolders within each device backup folder.
- **FR-04** The application shall distinguish between photo file types (JPEG, PNG, HEIC, RAW variants, etc.) and video file types (MP4, MOV, MKV, AVI, etc.).
- **FR-04a†** The user shall be able to cancel a running scan at any time; the scanner shall stop cleanly after processing the current file without requiring a server restart.
- **FR-04b†** Upon scan completion the UI shall display the number of new files found per device, so the user can immediately verify which devices synced new content.

### 3.2 Destination Management

- **FR-05** The application shall maintain a configured photos library root and a separate videos library root.
- **FR-06** The application shall allow the user to select any existing folder within the library as a destination, navigated via a hierarchical tree that loads children lazily on expansion.
- **FR-07** The application shall allow the user to create new folders at any nesting depth within the library, including immediately inside a just-created folder.
- **FR-08** New destination folders shall only be created on the filesystem at the moment a file is actually moved into them; no speculative or empty folders shall be created in advance.
- **FR-09†** The application shall display, for each destination zone, how many files already exist in the target folder (separately for photos and videos) and how many files are currently staged to be moved there.
- **FR-10†** Destination zone selections shall be persisted in the browser (`localStorage`) and restored on the next page load.

*† New requirement added during implementation.*

### 3.3 File Processing

- **FR-11** The application shall move files from the backup location to the chosen destination (move, not copy, to avoid duplicate storage).
- **FR-12** The application shall read the capture date/time from file metadata (EXIF data for photos; container metadata for videos) with fallback to the file's last-modified date.
- **FR-13** The application shall detect duplicate files at the destination before moving (same size + SHA-256 hash) and skip them rather than overwriting existing files.
- **FR-14** The application shall skip a move when a file with the same filename already exists at the destination but is not a byte-for-byte duplicate, preventing silent data loss.
- **FR-15** The application shall preserve original filenames. Rename-on-collision is not performed; a same-name conflict results in a skip (see FR-14).
- **FR-16** The application shall log every file operation (moved, skipped, or error) with source path, destination path, and reason.
- **FR-17** The application shall allow the user to permanently delete source files from within the web UI, individually or in bulk, after an explicit confirmation step.
- **FR-18†** Deletion shall also be available from within the full-screen media preview, with automatic advancement to the next file after deletion.
- **FR-18a†** The application shall allow the user to delete duplicate backup files after confirmation to prevent them from reappearing in future scans and re-triggering duplicate detection.

*† New requirement added during implementation.*

### 3.4 User Workflow

- **FR-19** The application shall provide a web-based user interface accessible from within the local network (no public internet exposure required).
- **FR-20** The UI shall present unprocessed media grouped by source device and capture date, allowing the user to review them before any files are moved.
- **FR-21** The UI shall allow the user to assign individual files to a destination by dragging them onto a destination zone. Multi-select (Shift+Click range, Ctrl+Click toggle) enables batch assignment.
- **FR-21a†** The UI shall allow the user to assign the selected file(s) to a destination zone by pressing the corresponding digit key (1–9); each zone displays its shortcut number in a badge.
- **FR-21b†** Each device-·-date group header in the media grid shall provide a checkbox control that selects all visible files in that group when checked, deselects them all when unchecked, and shows an indeterminate state when only some files in the group are selected.
- **FR-21c†** The UI shall support undoing the most-recently-applied assignment batch via Ctrl/Cmd+Z (up to 50 levels); cards are restored to their previous zone or to unassigned.
- **FR-21d†** After the first assignment action the UI shall show a **Quick-assign** button (and respond to the `Q` key) that re-assigns the selected cards to the last-used destination zone.
- **FR-22** The UI shall allow the user to filter visible media cards by source device and sort them by date or GPS location. The selected filter and sort order shall be persisted in `localStorage` (`pbo_filter_sort_v1`) and restored on subsequent page loads.
- **FR-22a†** The destination badge on an assigned card shall display the destination label at all times and change to a ✕ indicator on hover to signal that clicking unassigns the file.
- **FR-22b†** When no destination zones are configured, the destinations panel shall display a styled onboarding hint guiding the user to create their first zone.
- **FR-23** The UI shall allow the user to browse and select existing library folders as destinations via a lazy-loading tree, or create new folders at any depth inline.
- **FR-24** The UI shall display a thumbnail preview for photos and a poster-frame preview for videos.
- **FR-24a†** The application shall probe each video's codec before serving a preview; videos already encoded as browser-native codecs (H.264/VP8/VP9/AV1) shall be streamed directly with no transcoding. Only non-native codecs (e.g. HEVC) shall be transcoded to H.264 on first open, with the result cached for subsequent playback.
- **FR-25** The UI shall support full-screen preview of individual media items with prev/next navigation and an inline delete action.
- **FR-26** The UI shall provide a confirmation step before files are physically moved, including a dry-run preview table.
- **FR-27** The UI shall display move progress during execution and a processing log after each batch move operation.
- **FR-28†** The UI action buttons (Delete, Dry-run, Move) shall remain visible while the user scrolls the media grid.
- **FR-29†** Scan operations shall be logged to the audit log (start, completion, error).
- **FR-30†** The audit log shall be viewable in the web UI as a live-updating HTML table.
- **FR-30a†** The audit log table shall support filtering by action type (All / Moves / Skips / Errors / Deletes / Scan events) via one-click filter buttons without a page reload.
- **FR-30b†** Each source and destination path cell in the audit log table shall provide a copy-to-clipboard button so users can locate files without SSH access.

*† New requirement added during implementation.*

### 3.5 Configuration

- **FR-31** All configurable values shall be stored in a single configuration file (YAML or TOML) mounted into the container at a well-known path.
- **FR-32** The configuration shall support:
  - A list of backup source folders, each with a human-readable device label.
  - The photos library root path.
  - The videos library root path.
  - Supported photo and video file extensions (with sensible defaults).
  - The port on which the web UI is served.
- **FR-33** Configuration changes shall take effect on application restart without rebuilding the container image.

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
