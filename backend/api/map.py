"""Lane-Aware Intelligent Emergency Vehicle Alert System (EVAS / AMBULANE)
Map Tile Proxy and Offline Caching Service.

Provides a same-origin map tile endpoint for client devices (desktops, laptops,
and mobile smartphones accessing via LAN Wi-Fi).

Core Problems Solved:
1. Mobile devices on LAN (e.g. http://10.70.34.155:8000) have no referer or cross-origin
   restrictions when fetching directly from openstreetmap.org, causing OSM servers to
   return 'x-blocked: No referer sent' error tiles.
2. Phones connected to laptop Wi-Fi hotspot frequently lack direct internet/DNS routing
   to tile.openstreetmap.org.
3. OpenStreetMap tile rate-limiting and network latency are eliminated by caching
   downloaded tiles to disk locally (backend/cache/tiles/).
4. Multi-tier upstream fallbacks (OpenStreetMap -> CartoDB Voyager -> Dynamic Fallback).
"""

from __future__ import annotations

import io
import logging
import os
import pathlib
import urllib.request
import urllib.error
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Path, Response, status
from fastapi.responses import FileResponse

logger = logging.getLogger("backend.api.map")

router = APIRouter(prefix="/api/map", tags=["map"])

# Disk cache directory for tiles
_CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / "cache" / "tiles"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Upstream tile sources with user agent and referer headers
_OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_CARTO_TILE_URL = "https://{sub}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"
_REQUEST_HEADERS = {
    "User-Agent": "EVAS-EmergencyAlert/1.0 (Lane-Aware Intelligent Alert System; contact: support@evas.local)",
    "Referer": "https://www.openstreetmap.org/",
    "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
}

_FALLBACK_TILE_BYTES: bytes | None = None


def _get_fallback_tile() -> bytes:
    """Generate a clean 256x256 dark-themed fallback tile with subtle grid."""
    global _FALLBACK_TILE_BYTES
    if _FALLBACK_TILE_BYTES is not None:
        return _FALLBACK_TILE_BYTES

    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (256, 256), (18, 18, 20, 255))
        draw = ImageDraw.Draw(img)
        # Subtle grid borders
        draw.rectangle([0, 0, 255, 255], outline=(35, 35, 42, 255), width=1)
        # Diagonal corner accent
        draw.line([(0, 0), (8, 8)], fill=(45, 45, 55, 255), width=1)
        draw.line([(256, 0), (248, 8)], fill=(45, 45, 55, 255), width=1)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        _FALLBACK_TILE_BYTES = buf.getvalue()
    except Exception:
        # Fallback 1x1 dark PNG if Pillow fails
        _FALLBACK_TILE_BYTES = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\x18\x18\x18"
            b"\x18\x00\x00\x00\x05\x00\x01\x15\x84\x8e\x12\x00\x00\x00\x00IEND\xaeB`\x82"
        )
    return _FALLBACK_TILE_BYTES


@router.api_route("/tiles/{z}/{x}/{y}.png", methods=["GET", "HEAD"])
async def get_map_tile(
    z: int = Path(..., ge=0, le=19, description="Zoom level (0-19)"),
    x: int = Path(..., ge=0, description="Tile X coordinate"),
    y: int = Path(..., ge=0, description="Tile Y coordinate"),
) -> Response:
    """Fetch, cache, and serve map tiles to local and LAN client devices.

    - Validates tile coordinates against max 2^z boundaries.
    - Serves from fast local disk cache if already downloaded.
    - Fetches from OpenStreetMap upstream with valid User-Agent & Referer.
    - Gracefully fails over to CartoDB and local fallback on network errors.
    """
    max_coord = (1 << z) - 1
    if x > max_coord or y > max_coord:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Coordinate ({x}, {y}) out of range for zoom level {z}",
        )

    tile_path = _CACHE_DIR / str(z) / str(x) / f"{y}.png"

    # 1. Check local disk cache
    if tile_path.exists():
        try:
            if tile_path.stat().st_size > 200:
                return FileResponse(
                    str(tile_path),
                    media_type="image/png",
                    headers={
                        "Cache-Control": "public, max-age=604800, immutable",
                        "X-Tile-Source": "cache",
                    },
                )
        except OSError:
            pass

    # 2. Fetch from upstream with automatic fallbacks
    # Upstream 1: OpenStreetMap standard tile
    osm_url = _OSM_TILE_URL.format(z=z, x=x, y=y)
    tile_data: bytes | None = None
    tile_source: str = "upstream-osm"

    try:
        req = urllib.request.Request(osm_url, headers=_REQUEST_HEADERS)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            # Check for OSM policy block header
            if resp.status == 200 and not resp.headers.get("x-blocked"):
                data = resp.read()
                if len(data) > 200 and data[:8].startswith(b"\x89PNG"):
                    tile_data = data
    except Exception as exc:
        logger.debug("OSM tile fetch failed for %d/%d/%d: %s", z, x, y, exc)

    # Upstream 2: CartoDB Voyager fallback if OSM is blocked or slow
    if tile_data is None:
        sub = ["a", "b", "c", "d"][(x + y) % 4]
        carto_url = _CARTO_TILE_URL.format(sub=sub, z=z, x=x, y=y)
        try:
            req = urllib.request.Request(carto_url, headers={"User-Agent": _REQUEST_HEADERS["User-Agent"]})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 200 and data[:8].startswith(b"\x89PNG"):
                        tile_data = data
                        tile_source = "upstream-cartodb"
        except Exception as exc:
            logger.debug("CartoDB tile fetch failed for %d/%d/%d: %s", z, x, y, exc)

    # 3. Save to disk cache if valid
    if tile_data is not None:
        try:
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            tile_path.write_bytes(tile_data)
        except OSError as exc:
            logger.warning("Failed writing tile cache %s: %s", tile_path, exc)

        return Response(
            content=tile_data,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=604800, immutable",
                "X-Tile-Source": tile_source,
            },
        )

    # 4. Return clean fallback tile if offline / upstream unavailable
    fallback = _get_fallback_tile()
    return Response(
        content=fallback,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=60",
            "X-Tile-Source": "fallback-offline",
        },
    )


@router.get("/status")
async def map_proxy_status() -> Dict[str, Any]:
    """Return status and diagnostics for the map tile proxy and cache."""
    tile_count = 0
    total_bytes = 0
    try:
        if _CACHE_DIR.exists():
            for p in _CACHE_DIR.rglob("*.png"):
                tile_count += 1
                total_bytes += p.stat().st_size
    except OSError:
        pass

    return {
        "status": "online",
        "provider": "OpenStreetMap + CartoDB Failover (Backend Proxy)",
        "api_key_required": False,
        "api_key_status": "None required - 100% Free & Open-Source OpenStreetMap",
        "cache_directory": str(_CACHE_DIR),
        "cached_tiles_count": tile_count,
        "cache_size_bytes": total_bytes,
        "endpoint_template": "/api/map/tiles/{z}/{x}/{y}.png",
    }
