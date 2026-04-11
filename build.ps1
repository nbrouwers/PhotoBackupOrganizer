#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Builds Photo Backup Organizer for multiple Docker platforms, including
    Synology NAS (amd64, arm64, arm/v7).

.DESCRIPTION
    Uses Docker Buildx + QEMU binfmt emulation to produce a multi-architecture
    image manifest.

    Synology NAS platform reference:
      linux/amd64   — Intel/AMD models (DS220+, DS420+, DS720+, DS920+, DS923+)
      linux/arm64   — ARM64 models     (DS223j, DS423j — Realtek RTD1619B)
      linux/arm/v7  — ARMv7 models     (older value-line)

    Multi-platform manifests cannot be loaded into a local Docker daemon.
    Use -Push to publish to a registry, -ExportOci to produce per-platform
    OCI tarballs for air-gapped NAS deployment, or -LoadAmd64 for local
    single-platform testing.

.PARAMETER Tag
    Docker image tag.  Default: latest

.PARAMETER Registry
    Registry + repository prefix.
    Docker Hub : "myuser"
    GHCR       : "ghcr.io/myorg/photo-backup-organizer"
    Omit when not pushing.

.PARAMETER ImageName
    Image name (without registry prefix).  Default: photo-backup-organizer

.PARAMETER Platforms
    Comma-separated platform list.
    Default: "linux/amd64,linux/arm64,linux/arm/v7"

.PARAMETER Push
    Build all platforms and push the manifest to the registry.

.PARAMETER LoadAmd64
    Build only linux/amd64 and load it into the local Docker daemon.
    Useful for local testing; cannot be combined with multi-platform builds.

.PARAMETER ExportOci
    Export each platform as an OCI tarball to ./dist/<platform>.tar.
    Use this for offline / air-gapped NAS deployment.

.PARAMETER BuilderName
    Buildx builder instance name.  Default: photo-backup-builder

.EXAMPLE
    # Build all platforms and push to Docker Hub
    .\build.ps1 -Registry myuser -Push

.EXAMPLE
    # Build and load linux/amd64 locally for quick testing
    .\build.ps1 -LoadAmd64

.EXAMPLE
    # Build only ARM64 (DS223j etc.) and push to GHCR
    .\build.ps1 -Registry ghcr.io/myorg/photo-backup-organizer -Platforms linux/arm64 -Push

.EXAMPLE
    # Export all platforms as OCI tarballs for offline NAS deployment
    .\build.ps1 -ExportOci
#>

[CmdletBinding(DefaultParameterSetName = 'MultiPush')]
param (
    [string]$Tag         = "latest",
    [string]$Registry    = "",
    [string]$ImageName   = "photo-backup-organizer",
    [string]$Platforms   = "linux/amd64,linux/arm64,linux/arm/v7",
    [string]$BuilderName = "photo-backup-builder",

    [Parameter(ParameterSetName = 'MultiPush')]
    [switch]$Push,

    [Parameter(ParameterSetName = 'LoadLocal')]
    [switch]$LoadAmd64,

    [Parameter(ParameterSetName = 'ExportOci')]
    [switch]$ExportOci
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Helpers ──────────────────────────────────────────────────────────────────
function Write-Step([string]$msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "    WARN $msg" -ForegroundColor Yellow }

# ── Prerequisites ─────────────────────────────────────────────────────────────
Write-Step "Checking prerequisites"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not installed or not in PATH. Install Docker Desktop and retry."
}

$dockerVer  = docker version --format '{{.Server.Version}}' 2>$null
Write-Ok "Docker $dockerVer"

$buildxVer = docker buildx version 2>$null
if (-not $buildxVer) {
    throw "Docker Buildx not found. Upgrade to Docker Desktop >= 4.x."
}
Write-Ok "Buildx: $buildxVer"

# ── Full image reference ──────────────────────────────────────────────────────
$fullImage = if ($Registry) { "$Registry/$ImageName" } else { $ImageName }
$fullRef   = "${fullImage}:${Tag}"

# ════════════════════════════════════════════════════════════════════════════
# MODE A — LoadAmd64: quick local single-platform build
# ════════════════════════════════════════════════════════════════════════════
if ($LoadAmd64) {
    Write-Step "Building linux/amd64 → local Docker daemon"
    Write-Ok "Tag: $fullRef"
    docker build --platform linux/amd64 -t $fullRef .
    if ($LASTEXITCODE -ne 0) { throw "docker build failed." }
    Write-Step "Done"
    Write-Ok "Test locally:  docker run --rm -p 8000:8000 $fullRef"
    exit 0
}

# ════════════════════════════════════════════════════════════════════════════
# Remaining modes need a multi-platform Buildx builder
# ════════════════════════════════════════════════════════════════════════════
Write-Step "Setting up Buildx builder '$BuilderName'"

$builderList = (docker buildx ls 2>$null) -join "`n"
if ($builderList -notmatch [regex]::Escape($BuilderName)) {
    Write-Ok "Creating builder with docker-container driver"
    docker buildx create --name $BuilderName --driver docker-container --bootstrap
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Buildx builder." }
} else {
    Write-Ok "Reusing existing builder '$BuilderName'"
}

docker buildx use $BuilderName
if ($LASTEXITCODE -ne 0) { throw "Failed to select builder." }

# Register QEMU binfmt handlers for cross-platform emulation
Write-Step "Registering QEMU binfmt handlers"
docker run --rm --privileged tonistiigi/binfmt --install all 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Warn "QEMU registration returned non-zero (may already be registered — continuing)."
}
Write-Ok "QEMU handlers ready"

# ════════════════════════════════════════════════════════════════════════════
# MODE B — ExportOci: build and export per-platform OCI tarballs
# ════════════════════════════════════════════════════════════════════════════
if ($ExportOci) {
    $distDir = Join-Path $PSScriptRoot "dist"
    Write-Step "Exporting platforms to OCI tarballs in $distDir"
    New-Item -ItemType Directory -Path $distDir -Force | Out-Null

    foreach ($platform in ($Platforms -split "," | ForEach-Object { $_.Trim() })) {
        $safeName = $platform -replace "/", "-"
        $destFile = Join-Path $distDir "${safeName}.tar"
        Write-Ok "Building $platform → $destFile"
        docker buildx build `
            --platform $platform `
            --output "type=oci,dest=$destFile" `
            -t $fullRef `
            .
        if ($LASTEXITCODE -ne 0) { throw "Build failed for platform: $platform" }
    }

    Write-Step "Export complete"
    Write-Host @"

To deploy an OCI tarball on Synology NAS (via SSH):
  scp ./dist/linux-amd64.tar user@nas:/volume1/docker/
  ssh user@nas
  docker load -i /volume1/docker/linux-amd64.tar   # or linux-arm64.tar / linux-arm-v7.tar

"@ -ForegroundColor Green
    exit 0
}

# ════════════════════════════════════════════════════════════════════════════
# MODE C — Multi-platform push (or dry-run verify build)
# ════════════════════════════════════════════════════════════════════════════
Write-Step "Multi-platform build"
Write-Ok "Platforms : $Platforms"
Write-Ok "Image     : $fullRef"
Write-Ok "Push      : $($Push.IsPresent)"

if ($Push -and -not $Registry) {
    Write-Warn "No -Registry specified; image name will be '$fullRef' (plain local name)."
    Write-Warn "For Docker Hub use: -Registry <username>"
}

$buildArgs = @(
    "buildx", "build",
    "--platform", $Platforms,
    "-t", $fullRef
)

if ($Push) {
    $buildArgs += "--push"
} else {
    # Build all platforms but do not push — validates cross-compilation without publishing
    $buildArgs += "--output", "type=image,push=false"
    Write-Warn "Dry-run: image NOT available locally (multi-arch manifests require a registry)."
    Write-Warn "Use -Push to publish, or -LoadAmd64 for local testing."
}

$buildArgs += "."

Write-Host ""
& docker @buildArgs
if ($LASTEXITCODE -ne 0) { throw "docker buildx build failed." }

Write-Step "Build complete"
if ($Push) {
    Write-Host @"

Image published: $fullRef

Deploy on Synology NAS:
  Option 1 — Container Manager GUI:
    Registry → search for '$fullImage' → Download → choose tag '$Tag'
    Then create container from the downloaded image.

  Option 2 — SSH:
    docker pull $fullRef
    cd /path/to/photo-backup-organizer
    docker-compose pull && docker-compose up -d

"@ -ForegroundColor Green
}
