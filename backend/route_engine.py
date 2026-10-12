"""Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 5 — Route Engine & Corridor Geometry

route_engine.py
===============
Route calculation (via OSRM) and corridor geometry definition.
Computes the ambulance's planned route and the route corridor that
defines which participant vehicles are in the path of the ambulance.

Public contract:
    get_route(start_lat, start_lng, end_lat, end_lng) -> Route
    get_route_corridor(route, corridor_width_m) -> Corridor
    is_point_in_corridor(point_lat, point_lng, corridor) -> bool
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import math
import os
from typing import List, Optional
import urllib.error
import urllib.request

logger = logging.getLogger("backend.route_engine")


@dataclass
class RoutePoint:
    """A single point along a route."""

    lat: float
    lng: float


@dataclass
class Route:
    """A computed route between two points.

    Attributes:
        points: Ordered list of RoutePoint forming the path.
        distance_m: Total route distance in metres (if known).
        duration_s: Estimated travel duration in seconds (if known).
        source: Identifier of the routing backend, e.g. "osrm", "graph".
    """

    points: List[RoutePoint] = field(default_factory=list)
    distance_m: Optional[float] = None
    duration_s: Optional[float] = None
    source: Optional[str] = None


@dataclass
class Corridor:
    """A corridor around a route.

    A corridor is the set of points within `width_m` of the route.
    Used to decide whether a participant vehicle is in the path of the ambulance.
    """

    route: Route
    width_m: float
    # Cached bounding box for fast rejection tests.
    min_lat: Optional[float] = None
    max_lat: Optional[float] = None
    min_lng: Optional[float] = None
    max_lng: Optional[float] = None


# ---------------------------------------------------------------------------
# Geodetic & Trigonometric Convenience Helpers
# ---------------------------------------------------------------------------
def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points on Earth, in metres."""
    r_earth_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth_m * c


def normalize_heading(deg: float) -> float:
    """Normalise a heading to the range [0, 360)."""
    return deg % 360.0


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial bearing in degrees (0=N, 90=E) from point 1 to point 2."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lng2 - lng1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


class RoutingError(Exception):
    """Raised when routing request fails or service is unavailable."""
    pass


class RouteEngine:
    """Base interface for route computation and spatial corridor checks."""

    def get_route(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
    ) -> Route:
        """Compute the route from (start_lat, start_lng) to (end_lat, end_lng)."""
        raise NotImplementedError("Subclasses must implement get_route")

    def get_route_corridor(self, route: Route, corridor_width_m: float) -> Corridor:
        """Build a corridor of `corridor_width_m` around the given route."""
        if not route.points:
            raise ValueError("Cannot build corridor for empty route")
        lats = [p.lat for p in route.points]
        lngs = [p.lng for p in route.points]
        lat_pad = corridor_width_m / 111139.0
        avg_lat = sum(lats) / len(lats)
        cos_lat = max(0.1, math.cos(math.radians(avg_lat)))
        lng_pad = corridor_width_m / (111139.0 * cos_lat)
        return Corridor(
            route=route,
            width_m=corridor_width_m,
            min_lat=min(lats) - lat_pad,
            max_lat=max(lats) + lat_pad,
            min_lng=min(lngs) - lng_pad,
            max_lng=max(lngs) + lng_pad,
        )

    def distance_to_segment_m(
        self,
        p_lat: float,
        p_lng: float,
        a_lat: float,
        a_lng: float,
        b_lat: float,
        b_lng: float,
    ) -> float:
        """Compute shortest distance in meters from point P to line segment AB."""
        r_earth = 6371000.0
        avg_lat = math.radians((a_lat + b_lat) / 2.0)
        cos_lat = max(0.1, math.cos(avg_lat))

        # Local Cartesian projection relative to A
        dx = r_earth * math.radians(b_lng - a_lng) * cos_lat
        dy = r_earth * math.radians(b_lat - a_lat)
        px = r_earth * math.radians(p_lng - a_lng) * cos_lat
        py = r_earth * math.radians(p_lat - a_lat)

        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-6:
            return math.sqrt(px * px + py * py)

        t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))
        proj_x = t * dx
        proj_y = t * dy
        return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

    def distance_to_corridor_m(
        self, point_lat: float, point_lng: float, corridor: Corridor
    ) -> float:
        """Compute the minimum distance in meters from point to route polyline."""
        pts = corridor.route.points
        if not pts:
            return float("inf")
        if len(pts) == 1:
            return haversine_distance_m(point_lat, point_lng, pts[0].lat, pts[0].lng)

        min_dist = float("inf")
        for i in range(len(pts) - 1):
            d = self.distance_to_segment_m(
                point_lat, point_lng,
                pts[i].lat, pts[i].lng,
                pts[i + 1].lat, pts[i + 1].lng,
            )
            if d < min_dist:
                min_dist = d
        return min_dist

    def is_point_in_corridor(
        self, point_lat: float, point_lng: float, corridor: Corridor
    ) -> bool:
        """Return True if (point_lat, point_lng) lies inside the corridor."""
        # Fast bounding box rejection
        if corridor.min_lat is not None and point_lat < corridor.min_lat:
            return False
        if corridor.max_lat is not None and point_lat > corridor.max_lat:
            return False
        if corridor.min_lng is not None and point_lng < corridor.min_lng:
            return False
        if corridor.max_lng is not None and point_lng > corridor.max_lng:
            return False

        dist = self.distance_to_corridor_m(point_lat, point_lng, corridor)
        return dist <= corridor.width_m


class OSRMRouteEngine(RouteEngine):
    """Production route engine integrating the OSRM HTTP API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("OSRM_BASE_URL")
            or "https://router.project-osrm.org"
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_route(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
    ) -> Route:
        """Fetch driving route geometry from OSRM service."""
        # OSRM expects coordinates in {longitude},{latitude} order
        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{start_lng:.6f},{start_lat:.6f};{end_lng:.6f},{end_lat:.6f}"
            f"?overview=full&geometries=geojson"
        )
        logger.info("Requesting OSRM route: %s", url)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LaneAwareEmergencySystem/1.0"},
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status != 200:
                    raise RoutingError(f"OSRM returned HTTP status {resp.status}")
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.error("OSRM route request failed: %s", exc)
            raise RoutingError(f"Route service unavailable: {exc}") from exc

        if data.get("code") != "Ok" or not data.get("routes"):
            msg = data.get("message", "No route found between coordinates")
            logger.error("OSRM routing failed: %s", msg)
            raise RoutingError(f"Routing failed: {msg}")

        route_data = data["routes"][0]
        coords = route_data["geometry"]["coordinates"]
        points = [RoutePoint(lat=c[1], lng=c[0]) for c in coords]

        return Route(
            points=points,
            distance_m=float(route_data.get("distance", 0.0)),
            duration_s=float(route_data.get("duration", 0.0)),
            source="osrm",
        )


def create_default_route_engine() -> RouteEngine:
    """Factory used by main.py to build the route engine."""
    return OSRMRouteEngine()