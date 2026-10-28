"""Lane-Aware Intelligent Emergency Vehicle Alert System
PHASES 3 & 4: Active Ambulance Journey Management & Route Corridor Tracking.

Responsibilities:
- Stores the active emergency journey (origin, destination, road-following route points, assigned lane).
- Prevents concurrent invalid journeys and supports clean Start / Stop lifecycle.
- Automatically constructs and updates the route Corridor for matching.
- Notifies connected clients via WebSocket dispatch.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from models import (
    ActiveJourney,
    AmbulanceConfigRequest,
    AmbulanceState,
    StartJourneyRequest,
    StopJourneyRequest,
)
from route_engine import Corridor, Route, RouteEngine, RoutePoint

logger = logging.getLogger("backend.journey_service")

AMBULANCE_ADMIN_PIN = os.environ.get("AMBULANCE_ADMIN_PIN", "9911")


class JourneyService:
    """Thread-safe service tracking active ambulance emergency journeys."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_journey: Optional[ActiveJourney] = None
        self._active_corridor: Optional[Corridor] = None
        self._route_engine = RouteEngine()

    def get_active_journey(self) -> Optional[ActiveJourney]:
        """Return the currently active journey, or None."""
        with self._lock:
            return self._active_journey

    def get_active_corridor(self) -> Optional[Corridor]:
        """Return the corridor corresponding to the active journey, or None."""
        with self._lock:
            return self._active_corridor

    def start_journey(self, req: StartJourneyRequest) -> ActiveJourney:
        """Validate and activate an emergency ambulance journey."""
        with self._lock:
            # 1. Validation
            if not req.ambulance_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ambulance_id is required",
                )

            # Coordinate validation
            for lat, lng, name in [
                (req.origin_lat, req.origin_lng, "Origin"),
                (req.destination_lat, req.destination_lng, "Destination"),
            ]:
                if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{name} coordinates ({lat}, {lng}) are invalid",
                    )
                if lat == 0.0 and lng == 0.0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{name} coordinates cannot be (0,0)",
                    )

            # Normalize assigned lane
            assigned_lane = req.assigned_lane.strip().upper()
            if assigned_lane not in ("LEFT", "CENTER", "RIGHT"):
                assigned_lane = "CENTER"

            # 2. Build Route and Corridor
            route_pts: List[RoutePoint] = []
            if req.route_points:
                for pt in req.route_points:
                    p_lat = pt.get("lat")
                    p_lng = pt.get("lng")
                    if p_lat is not None and p_lng is not None:
                        route_pts.append(RoutePoint(lat=float(p_lat), lng=float(p_lng)))

            # Fallback to straight segment between origin and destination if route_points empty
            if len(route_pts) < 2:
                route_pts = [
                    RoutePoint(lat=req.origin_lat, lng=req.origin_lng),
                    RoutePoint(lat=req.destination_lat, lng=req.destination_lng),
                ]

            route_obj = Route(
                points=route_pts,
                distance_m=req.distance_meters,
                duration_s=req.duration_seconds,
                source="google_maps" if req.route_points else "direct",
            )
            # Default road corridor width: 35 meters half-width (70m total corridor)
            corridor_obj = self._route_engine.get_route_corridor(route_obj, corridor_width_m=35.0)

            # 3. Create ActiveJourney record
            journey_id = f"JRN_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            journey = ActiveJourney(
                journey_id=journey_id,
                ambulance_id=req.ambulance_id,
                origin_name=req.origin_name or f"Origin ({req.origin_lat:.4f}, {req.origin_lng:.4f})",
                origin_lat=req.origin_lat,
                origin_lng=req.origin_lng,
                destination_name=req.destination_name or f"Destination ({req.destination_lat:.4f}, {req.destination_lng:.4f})",
                destination_lat=req.destination_lat,
                destination_lng=req.destination_lng,
                route_points=[{"lat": p.lat, "lng": p.lng} for p in route_pts],
                distance_meters=req.distance_meters,
                duration_seconds=req.duration_seconds,
                assigned_lane=assigned_lane,
                is_active=True,
                started_at=time.time(),
                stopped_at=None,
            )

            self._active_journey = journey
            self._active_corridor = corridor_obj

            # 4. Synchronize fixed lane with device_service
            try:
                from device_service import get_device_service
                get_device_service().update_ambulance_config(
                    AmbulanceConfigRequest(
                        ambulance_id=req.ambulance_id,
                        configured_lane=assigned_lane,
                        configured_approach="NORTH_SOUTH",
                    )
                )
            except Exception as exc:
                logger.warning("Could not sync ambulance config in device_service: %s", exc)

            # 5. Update ambulance state emergency flag in websocket_manager
            try:
                from websocket_manager import get_ws_manager
                ws_mgr = get_ws_manager()
                amb_state = ws_mgr.ambulance_state
                if amb_state is not None:
                    # Activate emergency mode
                    new_amb = AmbulanceState(
                        lat=amb_state.lat,
                        lng=amb_state.lng,
                        speed_kmh=amb_state.speed_kmh,
                        heading_deg=amb_state.heading_deg,
                        emergency=True,
                        ts=time.time(),
                        ambulance_id=req.ambulance_id,
                        received_at=time.time(),
                    )
                    ws_mgr.set_ambulance_state(new_amb)
            except Exception as exc:
                logger.warning("Could not update ambulance state emergency flag: %s", exc)

            logger.info(
                "Journey %s STARTED for ambulance %s (lane=%s, %d points, %.1fm)",
                journey_id,
                req.ambulance_id,
                assigned_lane,
                len(route_pts),
                req.distance_meters,
            )
            return journey

    def stop_journey(self, req: StopJourneyRequest) -> Dict[str, Any]:
        """Safely terminate the current emergency journey."""
        with self._lock:
            if self._active_journey is None:
                return {
                    "status": "not_active",
                    "message": "No emergency journey is currently active",
                    "ambulance_id": req.ambulance_id,
                }

            stopped_journey = self._active_journey
            stopped_journey.is_active = False
            stopped_journey.stopped_at = time.time()

            self._active_journey = None
            self._active_corridor = None

            # Reset ambulance emergency state in websocket_manager
            try:
                from websocket_manager import get_ws_manager
                ws_mgr = get_ws_manager()
                amb_state = ws_mgr.ambulance_state
                if amb_state is not None:
                    new_amb = AmbulanceState(
                        lat=amb_state.lat,
                        lng=amb_state.lng,
                        speed_kmh=amb_state.speed_kmh,
                        heading_deg=amb_state.heading_deg,
                        emergency=False,
                        ts=time.time(),
                        ambulance_id=req.ambulance_id,
                        received_at=time.time(),
                    )
                    ws_mgr.set_ambulance_state(new_amb)
            except Exception as exc:
                logger.warning("Could not clear emergency flag in ambulance state: %s", exc)

            logger.info("Journey %s STOPPED for ambulance %s", stopped_journey.journey_id, req.ambulance_id)
            return {
                "status": "stopped",
                "journey_id": stopped_journey.journey_id,
                "ambulance_id": req.ambulance_id,
                "stopped_at": stopped_journey.stopped_at,
            }


_journey_service: Optional[JourneyService] = None


def get_journey_service() -> JourneyService:
    global _journey_service
    if _journey_service is None:
        _journey_service = JourneyService()
    return _journey_service
