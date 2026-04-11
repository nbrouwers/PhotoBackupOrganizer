# Target platform: linux/amd64 (Intel/AMD 64-bit)
# Synology NAS: Celeron J4025 and other Intel 64-bit models
# ── Builder stage ──────────────────────────────────────────────────────────────
FROM --platform=linux/amd64 python:3.12-slim-bookworm AS builder

WORKDIR /build

# Install build tools needed by some wheels (e.g. Pillow native libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a venv and install Python deps into it
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .


# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM --platform=linux/amd64 python:3.12-slim-bookworm AS runtime

# ffmpeg supplies both ffprobe (video metadata) and the ffmpeg binary
# (video poster frames).  The Debian bookworm repo ships ffmpeg 5.x with
# broad H.264/HEVC/AAC support; no recompilation needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    && rm -rf /var/lib/apt/lists/*

# Copy the venv from the builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY app/ ./app/

# Mounted at runtime (see docker-compose.yml):
#   /config   – config.yaml
#   /backups  – phone backup folders (read-write, files are moved out)
#   /photos   – photos library root  (read-write)
#   /videos   – videos library root  (read-write)
#   /logs     – persistent audit log (read-write)
#   /cache    – thumbnail cache      (read-write)

ENV PHOTO_BACKUP_CONFIG=/config/config.yaml

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
