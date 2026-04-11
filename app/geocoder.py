"""Reverse geocoding via Nominatim (OpenStreetMap).

GPS coordinates extracted from EXIF are looked up at most once — results are
persisted in the ``location_cache`` SQLite table so they survive container
restarts.  The Nominatim usage policy requires ≤ 1 request/second; this is
enforced with a semaphore + asyncio.sleep.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from typing import Optional

from app.database import get_cached_location, set_cached_location

logger = logging.getLogger(__name__)

_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "PhotoBackupOrganizer/1.0 (personal-nas-photo-organizer)"

# Round to ~1 km grid for cache key deduplication
_CACHE_PRECISION = 2

# Serialise outbound requests; asyncio.sleep below enforces ≤ 1 req/s
_sem = asyncio.Semaphore(1)


def _coord_key(lat: float, lon: float) -> str:
    return f"{round(lat, _CACHE_PRECISION)},{round(lon, _CACHE_PRECISION)}"


def _fetch_nominatim(lat: float, lon: float) -> str:
    """Synchronous HTTP call — always run in an executor."""
    url = (
        f"{_NOMINATIM}?lat={lat}&lon={lon}"
        "&format=jsonv2&zoom=10&addressdetails=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    addr = data.get("address", {})
    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("hamlet")
        or addr.get("county")
        or ""
    )
    country = addr.get("country") or addr.get("country_code", "").upper()
    parts = [p for p in (city, country) if p]
    return ", ".join(parts)


async def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Return a human-readable ``"City, Country"`` string, or ``None`` on failure.

    Results are cached permanently in SQLite; ``""`` means a previous lookup
    returned no data and is stored to avoid repeated failed requests.
    """
    key = _coord_key(lat, lon)

    # Fast path: cache hit (no lock needed)
    cached = await get_cached_location(key)
    if cached is not None:
        return cached or None  # "" → previously looked up, no result

    async with _sem:
        # Re-check after acquiring lock (another coroutine may have fetched)
        cached = await get_cached_location(key)
        if cached is not None:
            return cached or None

        try:
            loop = asyncio.get_running_loop()
            location = await loop.run_in_executor(None, _fetch_nominatim, lat, lon)
            await set_cached_location(key, location)
            await asyncio.sleep(1.05)   # respect ≤ 1 req/s Nominatim policy
            return location or None
        except Exception as exc:
            logger.debug("Nominatim lookup failed for (%s, %s): %s", lat, lon, exc)
            return None
