"""FastAPI application entry point."""

from __future__ import annotations

import base64
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_config
from app.database import close_db
from app.routers import destinations, move, scan, ui

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Photo Backup Organizer starting up")
    cfg = get_config()
    logger.info(
        "Config loaded: %d device(s), photos_root=%s, videos_root=%s",
        len(cfg.devices),
        cfg.library.photos_root,
        cfg.library.videos_root,
    )
    yield
    await close_db()
    logger.info("Photo Backup Organizer shut down")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    cfg = get_config()

    application = FastAPI(
        title="Photo Backup Organizer",
        description="Organizes phone backup photos and videos into a curated NAS library",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Optional HTTP Basic Auth (NFR-06)
    if cfg.security and cfg.security.basic_auth:
        ba = cfg.security.basic_auth
        logger.info("HTTP Basic Auth enabled for user '%s'", ba.username)
        application.add_middleware(BasicAuthMiddleware, username=ba.username, password=ba.password)

    # Routers
    application.include_router(scan.router)
    application.include_router(destinations.router)
    application.include_router(move.router)
    application.include_router(ui.router)

    # Thumbnail serving: GET /thumbnails?src=<source_path>
    @application.get("/thumbnails")
    async def serve_thumbnail(src: str):
        """Return a cached thumbnail for the given source media path.

        Generates the thumbnail on the fly if it is not yet cached.
        """
        from app.thumbnails import get_thumbnail
        from app.metadata import get_media_type

        media_type = get_media_type(src)
        thumb_path_str = await get_thumbnail(src, media_type or "photo")
        if not thumb_path_str or not Path(thumb_path_str).exists():
            return JSONResponse(status_code=404, content={"detail": "Thumbnail not available"})
        return FileResponse(thumb_path_str, media_type="image/jpeg")

    # H.264 preview: GET /video-preview?src=<source_path>
    @application.get("/video-preview")
    async def serve_video_preview(src: str):
        """Return an H.264/AAC MP4 preview clip for the given video source path.

        Transcodes the first 15 seconds to H.264 so all browsers (including
        those without HEVC support) can play the video track.  The result is
        cached; the first request for a given file may take 5–30 s.

        Security: only paths inside configured device backup roots are allowed.
        """
        from app.thumbnails import generate_video_preview

        # Same path-traversal guard as /media
        cfg           = get_config()
        allowed_roots = [Path(d.path).resolve() for d in cfg.devices]
        file_path     = Path(src).resolve()
        if not any(file_path.is_relative_to(root) for root in allowed_roots):
            raise HTTPException(status_code=403, detail="Access denied: path outside device roots")
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Source file not found")

        preview_path = await generate_video_preview(src)
        if not preview_path or not Path(preview_path).exists():
            return JSONResponse(status_code=404, content={"detail": "Preview not available"})
        return FileResponse(preview_path, media_type="video/mp4")

    return application


# ---------------------------------------------------------------------------
# Basic Auth middleware (NFR-06)
# ---------------------------------------------------------------------------


class BasicAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, username: str, password: str) -> None:
        super().__init__(app)
        self._credentials = base64.b64encode(
            f"{username}:{password}".encode()
        ).decode()

    async def dispatch(self, request: Request, call_next):
        # Allow health-check without auth
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Basic "):
            provided = auth_header[len("Basic "):]
            if secrets.compare_digest(provided, self._credentials):
                return await call_next(request)

        return Response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": 'Basic realm="Photo Backup Organizer"'},
            content="Unauthorized",
        )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

app = create_app()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
