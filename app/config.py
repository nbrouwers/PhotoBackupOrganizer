"""Configuration loader and validator.

The config file path is read from the environment variable
``PHOTO_BACKUP_CONFIG`` (default: ``/config/config.yaml``).

Call :func:`get_config` anywhere in the application to retrieve the validated,
singleton :class:`AppConfig` instance.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class DeviceConfig(BaseModel):
    label: str
    path: str

    @field_validator("path")
    @classmethod
    def path_must_be_absolute(cls, v: str) -> str:
        # Accept Linux-style absolute paths (start with /) for container config,
        # as well as Windows absolute paths (for local dev with native paths).
        if not (v.startswith("/") or Path(v).is_absolute()):
            raise ValueError(f"Device path must be absolute, got: {v!r}")
        return v


class LibraryConfig(BaseModel):
    photos_root: str
    videos_root: str

    @field_validator("photos_root", "videos_root")
    @classmethod
    def path_must_be_absolute(cls, v: str) -> str:
        if not (v.startswith("/") or Path(v).is_absolute()):
            raise ValueError(f"Library path must be absolute, got: {v!r}")
        return v


class ExtensionsConfig(BaseModel):
    photos: list[str] = Field(
        default=[".jpg", ".jpeg", ".png", ".heic", ".heif", ".dng", ".raw",
                 ".arw", ".nef", ".cr2", ".cr3", ".webp"]
    )
    videos: list[str] = Field(
        default=[".mp4", ".mov", ".m4v", ".mkv", ".avi", ".3gp", ".webm"]
    )

    @field_validator("photos", "videos", mode="before")
    @classmethod
    def normalise_extensions(cls, v: list[str]) -> list[str]:
        return [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in v]


class ServerConfig(BaseModel):
    port: int = 8000


class CacheConfig(BaseModel):
    path: str = "/cache"
    thumb_size: int = 300


class BasicAuthConfig(BaseModel):
    username: str
    password: str


class SecurityConfig(BaseModel):
    basic_auth: Optional[BasicAuthConfig] = None


class AppConfig(BaseModel):
    devices: list[DeviceConfig]
    library: LibraryConfig
    extensions: ExtensionsConfig = Field(default_factory=ExtensionsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    security: Optional[SecurityConfig] = None

    @property
    def all_photo_extensions(self) -> set[str]:
        return set(self.extensions.photos)

    @property
    def all_video_extensions(self) -> set[str]:
        return set(self.extensions.videos)

    @property
    def all_extensions(self) -> set[str]:
        return self.all_photo_extensions | self.all_video_extensions


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_CONFIG_ENV_VAR = "PHOTO_BACKUP_CONFIG"
_DEFAULT_CONFIG_PATH = "/config/config.yaml"


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Load, validate and cache the application configuration.

    Raises :class:`SystemExit` with a descriptive message when the config
    file is missing or invalid – intentionally fatal so the container does
    not start in a broken state.
    """
    config_path = Path(os.environ.get(_CONFIG_ENV_VAR, _DEFAULT_CONFIG_PATH))

    if not config_path.exists():
        raise SystemExit(
            f"Configuration file not found: {config_path}\n"
            f"Mount a config.yaml at that path or set the "
            f"{_CONFIG_ENV_VAR} environment variable."
        )

    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise SystemExit(f"Configuration file is empty or not valid YAML: {config_path}")

    try:
        return AppConfig.model_validate(raw)
    except Exception as exc:  # pydantic.ValidationError
        raise SystemExit(f"Invalid configuration in {config_path}:\n{exc}") from exc


def reload_config() -> AppConfig:
    """Clear the cache and reload the config from disk (useful in tests)."""
    get_config.cache_clear()
    return get_config()
