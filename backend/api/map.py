"""Lane-Aware Intelligent Emergency Vehicle Alert System (EVAS / AMBULANE)
Map Tile Proxy and Offline Caching Service.

Provides a compliant, same-origin map tile endpoint for client devices (desktops,
laptops, and mobile smartphones accessing via LAN IP http://<LAN-IP>:8000).

Features:
- Asynchronous fetching using httpx.AsyncClient with timeout and pooling.
- Strict compliance with OpenStreetMap Tile Usage Policy (custom User-Agent & Referer).
- Automatic upstream failover: OpenStreetMap -> CartoDB Voyager -> Dark fallback tile.
- Two-tier caching:
  1. Fast in-memory LRU cache (last 500 tiles) for microsecond responses.
  2. Persistent local disk cache (backend/data/tile_cache/{z}/{x}/{y}.png).
- Mobile-safe response headers:
  "Cache-Control": "public, max-age=86400"
  "Access-Control-Allow-Origin": "*"
"""

from __future__ import annotations

from collections import OrderedDict
import io
import logging
import os
import pathlib
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Path, Response, status
from fastapi.responses import FileResponse
import httpx

logger = logging.getLogger("backend.api.map")

router = APIRouter(prefix="/api/map", tags=["map"])

# Disk cache directory for tiles
_CACHE_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "tile_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# In-memory LRU cache for ultra-fast serving (up to 500 tiles)
_MAX_MEMORY_CACHE = 500
_MEMORY_CACHE: OrderedDict[str, bytes] = OrderedDict()

# Upstream tile sources
_OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_CARTO_TILE_URL = "https://{sub}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"

# Headers strictly compliant with OSM policy
_UPSTREAM_HEADERS = {
    "User-Agent": "AMBULANE-EVAS-Emergency-System/1.0 (https://github.com/ambulane-evas; contact@ambulane.local)",
    "Referer": "https://www.openstreetmap.org/",
    "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
}

_FALLBACK_TILE_BYTES: Optional[bytes] = None


def _get_fallback_tile() -> bytes:
    """Generate a clean 256x256 dark-themed fallback tile with subtle grid."""
    global _FALLBACK_TILE_BYTES
    if _FALLBACK_TILE_BYTES is not None:
        return _FALLBACK_TILE_BYTES

    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (256, 256), (18, 18, 20, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 255, 255], outline=(35, 35, 42, 255), width=1)
        draw.line([(0, 0), (8, 8)], fill=(45, 45, 55, 255), width=1)
        draw.line([(256, 0), (248, 8)], fill=(45, 45, 55, 255), width=1)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        _FALLBACK_TILE_BYTES = buf.getvalue()
    except Exception:
        # Fallback 1x1 dark PNG if Pillow is unavailable
        _FALLBACK_TILE_BYTES = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\x18\x18\x18"
            b"\x18\x00\x00\x00\x05\x00\x01\x15\x84\x8e\x12\x00\x00\x00\x00IEND\xaeB`\x82"
        )
    return _FALLBACK_TILE_BYTES


def _add_to_mem_cache(key: str, data: bytes) -> None:
    """Store tile in memory LRU cache."""
    if key in _MEMORY_CACHE:
        _MEMORY_CACHE.move_to_end(key)
    _MEMORY_CACHE[key] = data
    if len(_MEMORY_CACHE) > _MAX_MEMORY_CACHE:
        _MEMORY_CACHE.popitem(last=False)


@router.api_route("/tiles/{z}/{x}/{y}.png", methods=["GET", "HEAD"])
async def get_map_tile(
    z: int = Path(..., ge=0, le=19, description="Zoom level (0-19)"),
    x: int = Path(..., ge=0, description="Tile X coordinate"),
    y: int = Path(..., ge=0, description="Tile Y coordinate"),
) -> Response:
    """Fetch, cache, and serve map tiles to local and LAN client devices.

    - Validates tile coordinates against 2^z boundaries.
    - Checks in-memory LRU cache (< 1ms).
    - Checks local disk cache (backend/data/tile_cache/{z}/{x}/{y}.png).
    - Asynchronously fetches from OpenStreetMap with compliant User-Agent & Referer.
    - Automatically fails over to CartoDB on 403, 429, 5xx, or network errors.
    - Returns Response with 'Cache-Control: public, max-age=86400' and 'Access-Control-Allow-Origin: *'.
    """
    max_coord = (1 << z) - 1
    if x > max_coord or y > max_coord:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Coordinate ({x}, {y}) out of range for zoom level {z}",
        )

    tile_key = f"{z}/{x}/{y}"
    tile_path = _CACHE_DIR / str(z) / str(x) / f"{y}.png"

    # Standard response headers
    response_headers = {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=86400",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    }

    # 1. Check in-memory LRU cache
    if tile_key in _MEMORY_CACHE:
        _MEMORY_CACHE.move_to_end(tile_key)
        return Response(
            content=_MEMORY_CACHE[tile_key],
            media_type="image/png",
            headers={**response_headers, "X-Tile-Source": "mem-cache"},
        )

    # 2. Check local disk cache
    if tile_path.exists():
        try:
            if tile_path.stat().st_size > 150:
                data = tile_path.read_bytes()
                _add_to_mem_cache(tile_key, data)
                return Response(
                    content=data,
                    media_type="image/png",
                    headers={**response_headers, "X-Tile-Source": "disk-cache"},
                )
        except OSError:
            pass

    # 3. Asynchronous upstream fetch with failover
    tile_data: Optional[bytes] = None
    tile_source: str = "upstream-osm"

    async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
        # Try Primary: OpenStreetMap
        try:
            osm_url = _OSM_TILE_URL.format(z=z, x=x, y=y)
            resp = await client.get(osm_url, headers=_UPSTREAM_HEADERS)
            if resp.status_code == 200 and not resp.headers.get("x-blocked"):
                content = resp.content
                if len(content) > 150 and content[:8].startswith(b"\x89PNG"):
                    tile_data = content
            else:
                logger.debug("OSM tile rejected with status %d or x-blocked: %s", resp.status_code, resp.headers.get("x-blocked"))
        except Exception as exc:
            logger.debug("OSM tile fetch exception for %s: %s", tile_key, exc)

        # Try Failover: CartoDB Voyager if OSM fails (403, 429, 5xx, or network error)
        if tile_data is None:
            sub = ["a", "b", "c", "d"][(x + y) % 4]
            carto_url = _CARTO_TILE_URL.format(sub=sub, z=z, x=x, y=y)
            try:
                carto_headers = {
                    "User-Agent": _UPSTREAM_HEADERS["User-Agent"],
                    "Accept": _UPSTREAM_HEADERS["Accept"],
                }
                resp = await client.get(carto_url, headers=carto_headers)
                if resp.status_code == 200:
                    content = resp.content
                    if len(content) > 150 and content[:8].startswith(b"\x89PNG"):
                        tile_data = content
                        tile_source = "upstream-cartodb"
            except Exception as exc:
                logger.debug("CartoDB tile fetch exception for %s: %s", tile_key, exc)

    # 4. If valid tile acquired, save to disk & memory cache
    if tile_data is not None:
        try:
            tile_path.parent.mkdir(parents=True, exist_ok=True)
            tile_path.write_bytes(tile_data)
        except OSError as exc:
            logger.warning("Failed writing tile cache to %s: %s", tile_path, exc)

        _add_to_mem_cache(tile_key, tile_data)

        return Response(
            content=tile_data,
            media_type="image/png",
            headers={**response_headers, "X-Tile-Source": tile_source},
        )

    # 5. Offline Fallback tile if network is down or completely unreachable
    fallback = _get_fallback_tile()
    return Response(
        content=fallback,
        media_type="image/png",
        headers={**response_headers, "X-Tile-Source": "fallback-offline"},
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
        "memory_cached_tiles": len(_MEMORY_CACHE),
        "endpoint_template": "/api/map/tiles/{z}/{x}/{y}.png",
    }
