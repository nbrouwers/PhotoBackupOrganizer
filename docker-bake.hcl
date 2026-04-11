# ---------------------------------------------------------------------------
# docker-bake.hcl — declarative multi-platform build targets
#
# Usage:
#   docker buildx bake                          # amd64 only, loads locally
#   docker buildx bake multiplatform --push     # all NAS platforms
#   docker buildx bake nas-arm --push           # ARM-only (arm64 + arm/v7)
#
# Override variables on the command line:
#   IMAGE=myuser/photo-backup-organizer TAG=1.0.0 docker buildx bake multiplatform --push
# ---------------------------------------------------------------------------

# Full image reference, e.g. "myuser/photo-backup-organizer"
# or "ghcr.io/myorg/photo-backup-organizer"
variable "IMAGE" {
  default = "photo-backup-organizer"
}

variable "TAG" {
  default = "latest"
}

# ── Shared build settings ────────────────────────────────────────────────────
target "_base" {
  context    = "."
  dockerfile = "Dockerfile"
  tags       = ["${IMAGE}:${TAG}"]
}

# ── Build groups ─────────────────────────────────────────────────────────────

# Default: single amd64 build — loads into the local Docker daemon
group "default" {
  targets = ["local"]
}

target "local" {
  inherits  = ["_base"]
  platforms = ["linux/amd64"]
}

# All platforms relevant to Synology NAS:
#   linux/amd64   — Intel/AMD models  (DS220+, DS420+, DS720+, DS920+, DS923+)
#   linux/arm64   — ARM64 models      (DS223j, DS423j — Realtek RTD1619B)
#   linux/arm/v7  — ARMv7 models      (older value-line with Marvell/Realtek ARMv7)
#
# Requires --push (or --output) because multi-arch manifests cannot be loaded
# into a local Docker daemon:
#   IMAGE=myuser/photo-backup-organizer docker buildx bake multiplatform --push
target "multiplatform" {
  inherits  = ["_base"]
  platforms = [
    "linux/amd64",
    "linux/arm64",
    "linux/arm/v7",
  ]
}

# ARM-only variant — faster when you only need Synology ARM NAS models
target "nas-arm" {
  inherits  = ["_base"]
  platforms = [
    "linux/arm64",
    "linux/arm/v7",
  ]
}
