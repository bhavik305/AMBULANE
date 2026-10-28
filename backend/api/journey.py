"""Lane-Aware Intelligent Emergency Vehicle Alert System
PHASES 3 & 4: Journey REST Router & System Configuration.
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, status
from journey_service import get_journey_service
from route_engine import OSRMRouteEngine, RoutingError, RoutePoint
from models import (
    ActiveJourney,
    StartJourneyRequest,
    StopJourneyRequest,
)

logger = logging.getLogger("backend.api.journey")

router = APIRouter(tags=["journey"])


def _get_local_ip() -> str:
    """Determine best-effort LAN IPv4 address for local network access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Does not actually transmit packets: queries OS route table
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@router.post("/api/journey/start", response_model=ActiveJourney)
async def start_journey(req: StartJourneyRequest) -> ActiveJourney:
    """Start an emergency ambulance journey with origin, destination, and road route."""
    service = get_journey_service()
    journey = service.start_journey(req)

    # Dispatch fleet update immediately so all connected clients see the route
    try:
        from dispatch_service import dispatch_alerts_and_fleet
        await dispatch_alerts_and_fleet(corridor=service.get_active_corridor())
    except Exception as exc:
        logger.warning("Error dispatching fleet after journey start: %s", exc)

    return journey


@router.post("/api/journey/stop")
async def stop_journey(req: StopJourneyRequest) -> Dict[str, Any]:
    """Terminate the active emergency journey and clear corridor alerts."""
    service = get_journey_service()
    result = service.stop_journey(req)

    # Dispatch fleet update to clear road corridor on all client maps
    try:
        from dispatch_service import dispatch_alerts_and_fleet
        await dispatch_alerts_and_fleet(corridor=None)
    except Exception as exc:
        logger.warning("Error dispatching fleet after journey stop: %s", exc)

    return result


@router.get("/api/journey/active")
async def get_active_journey() -> Dict[str, Any]:
    """Return the current active journey or indicate none is running."""
    service = get_journey_service()
    journey = service.get_active_journey()
    if journey is None:
        return {"active": False, "journey": None}
    return {"active": True, "journey": journey.model_dump()}


@router.get("/api/journey/route")
async def calculate_route(
    origin_lat: float = Query(..., ge=-90.0, le=90.0),
    origin_lng: float = Query(..., ge=-180.0, le=180.0),
    dest_lat: float = Query(..., ge=-90.0, le=90.0),
    dest_lng: float = Query(..., ge=-180.0, le=180.0),
) -> Dict[str, Any]:
    """Calculate driving route between origin and destination coordinates using OSRM."""
    engine = OSRMRouteEngine(timeout_seconds=2.5)
    try:
        route = engine.get_route(origin_lat, origin_lng, dest_lat, dest_lng)
        points = [{"lat": pt.lat, "lng": pt.lng} for pt in route.points]
        return {
            "status": "ok",
            "source": "OSRM",
            "distance_meters": route.distance_m or 0.0,
            "duration_seconds": route.duration_s or 0.0,
            "points": points,
        }
    except RoutingError as exc:
        logger.warning("OSRM online calculation failed: %s. Using interpolated corridor.", exc)
        # Fallback to direct corridor points if routing service is unreachable
        pts = [
            {"lat": origin_lat, "lng": origin_lng},
            {"lat": (origin_lat * 2 + dest_lat) / 3.0, "lng": (origin_lng * 2 + dest_lng) / 3.0},
            {"lat": (origin_lat + dest_lat * 2) / 3.0, "lng": (origin_lng + dest_lng * 2) / 3.0},
            {"lat": dest_lat, "lng": dest_lng},
        ]
        # Approximate distance
        import math
        dlat = math.radians(dest_lat - origin_lat)
        dlng = math.radians(dest_lng - origin_lng)
        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(math.radians(origin_lat))
            * math.cos(math.radians(dest_lat))
            * math.sin(dlng / 2.0) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        dist_m = 6371000.0 * c
        duration_s = max(30.0, dist_m / 11.1)  # ~40 km/h average speed
        return {
            "status": "fallback",
            "source": "GEO_INTERPOLATION",
            "distance_meters": round(dist_m, 1),
            "duration_seconds": round(duration_s, 1),
            "points": pts,
        }

        duration_s = (dist_m / 11.1)  # ~40 km/h avg speed

        return {
            "status": "fallback",
            "source": "INTERPOLATED",
            "message": f"Online routing service unavailable ({exc}); interpolated corridor provided",
            "distance_meters": round(dist_m, 1),
            "duration_seconds": round(duration_s, 1),
            "points": pts,
        }


@router.get("/api/config")
async def get_app_config() -> Dict[str, Any]:
    """Return runtime frontend configuration including OpenStreetMap tile provider and LAN host.

    Secrets like admin PINs are NOT exposed here.
    """
    lan_ip = _get_local_ip()

    return {
        "map_provider": "openstreetmap",
        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors",
        "routing_service": "osrm",
        "lan_ip": lan_ip,
        "default_ws_url": f"ws://{lan_ip}:8000",
    }
