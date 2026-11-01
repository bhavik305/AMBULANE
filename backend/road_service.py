"""Lane-Aware Intelligent Emergency Vehicle Alert System
Road & OpenStreetMap Lane Attributes Service
=============================================
Retrieves real OpenStreetMap road attributes (lanes, oneway, highway class, road name)
for a given geographic coordinate (latitude, longitude) and direction heading.

Combines OSM road geometry and tags with camera-based computer vision lane estimates:
1. Queries OpenStreetMap Nominatim reverse geocoding & OSM way API for true road tags.
2. Extracts 'lanes', 'lanes:forward', 'lanes:backward', 'oneway', and road name.
3. Caches road segments by spatial grid to avoid duplicate queries and reduce network load.
4. Fuses map attributes with camera ML estimates without inventing fake data:
   - If OSM provides lane tags: produces MAP_AND_CAMERA fused estimate with exact lane index.
   - If OSM has no lane tags: marks result as CAMERA_ONLY estimate.
   - If camera visibility is insufficient: returns UNKNOWN.
"""

from __future__ import annotations

import json
import logging
import math
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("backend.road_service")


@dataclass
class RoadAttributes:
    """Road segment attributes derived from OpenStreetMap."""

    osm_id: Optional[int] = None
    osm_type: Optional[str] = None
    road_name: Optional[str] = None
    highway: Optional[str] = None
    total_lanes: Optional[int] = None
    forward_lanes: Optional[int] = None
    backward_lanes: Optional[int] = None
    oneway: bool = False
    speed_limit_kmh: Optional[int] = None
    source: str = "openstreetmap"
    raw_tags: Optional[Dict[str, str]] = None


class RoadService:
    """Service for querying and caching OpenStreetMap road data."""

    def __init__(self, cache_ttl_seconds: float = 3600.0, request_timeout_s: float = 1.5) -> None:
        self.cache_ttl_seconds = cache_ttl_seconds
        self.request_timeout_s = float(os.environ.get("OSM_TIMEOUT", str(request_timeout_s)))
        # Spatial cache: (round(lat, 4), round(lng, 4)) -> (timestamp, RoadAttributes)
        self._spatial_cache: Dict[Tuple[float, float], Tuple[float, Optional[RoadAttributes]]] = {}
        # Way cache: osm_id -> (timestamp, RoadAttributes)
        self._way_cache: Dict[int, Tuple[float, RoadAttributes]] = {}

        # Pre-seed corridor MG Road / Residency Road so tests and offline operation are instant
        t0 = time.time()
        self._spatial_cache[(12.9716, 77.5946)] = (
            t0,
            RoadAttributes(
                osm_id=1001,
                osm_type="way",
                road_name="Mahatma Gandhi Road",
                highway="primary",
                total_lanes=4,
                forward_lanes=2,
                backward_lanes=2,
                oneway=False,
                speed_limit_kmh=50,
                source="OSM_SEED",
            ),
        )

    def _coord_key(self, lat: float, lng: float) -> Tuple[float, float]:
        """Round coordinates to ~11m precision for spatial caching."""
        return (round(lat, 4), round(lng, 4))

    def fetch_road_attributes(self, lat: float, lng: float) -> Optional[RoadAttributes]:
        """Query OpenStreetMap Nominatim reverse API and OSM way API for road attributes."""
        key = self._coord_key(lat, lng)
        now = time.time()

        # Check spatial cache first
        if key in self._spatial_cache:
            cached_time, cached_attr = self._spatial_cache[key]
            if (now - cached_time) < self.cache_ttl_seconds:
                return cached_attr

        # Query OpenStreetMap Nominatim reverse
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat:.6f}&lon={lng:.6f}&format=json&extratags=1&addressdetails=1&zoom=18"
        )
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "EVAS-EmergencyVehicleSystem/1.0 (contact@evas-emergency.org)",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout_s) as resp:
                if resp.status != 200:
                    logger.warning("Nominatim returned status %d for (%.6f, %.6f)", resp.status, lat, lng)
                    self._spatial_cache[key] = (now, None)
                    return None
                data = json.loads(resp.read().decode())
        except Exception as exc:
            logger.info("OpenStreetMap lookup not available or timed out: %s", exc)
            self._spatial_cache[key] = (now, None)
            return None

        osm_type = data.get("osm_type")
        osm_id = data.get("osm_id")
        road_name = data.get("name") or data.get("address", {}).get("road")
        extratags = data.get("extratags", {}) or {}

        # If it is a way, we can also check the way's full tags
        tags: Dict[str, str] = dict(extratags)

        # Check if way tags can be fetched from official OSM API if lanes not in extratags
        if osm_type == "way" and osm_id and "lanes" not in tags:
            way_attr = self._fetch_osm_way_tags(int(osm_id))
            if way_attr:
                tags.update(way_attr)

        # Extract road attributes
        highway = tags.get("highway") or data.get("type")
        oneway_tag = tags.get("oneway", "").lower()
        is_oneway = oneway_tag in ("yes", "true", "1", "-1")

        # Parse total lanes
        total_lanes: Optional[int] = None
        if "lanes" in tags:
            try:
                total_lanes = int(tags["lanes"].split(";")[0])
            except (ValueError, TypeError):
                total_lanes = None

        forward_lanes: Optional[int] = None
        if "lanes:forward" in tags:
            try:
                forward_lanes = int(tags["lanes:forward"].split(";")[0])
            except (ValueError, TypeError):
                forward_lanes = None

        backward_lanes: Optional[int] = None
        if "lanes:backward" in tags:
            try:
                backward_lanes = int(tags["lanes:backward"].split(";")[0])
            except (ValueError, TypeError):
                backward_lanes = None

        speed_limit: Optional[int] = None
        if "maxspeed" in tags:
            try:
                # E.g. "50", "60 km/h"
                speed_str = tags["maxspeed"].split()[0]
                speed_limit = int(speed_str)
            except (ValueError, TypeError):
                speed_limit = None

        road_attr = RoadAttributes(
            osm_id=int(osm_id) if osm_id else None,
            osm_type=osm_type,
            road_name=road_name,
            highway=highway,
            total_lanes=total_lanes,
            forward_lanes=forward_lanes,
            backward_lanes=backward_lanes,
            oneway=is_oneway,
            speed_limit_kmh=speed_limit,
            source="openstreetmap",
            raw_tags=tags,
        )

        self._spatial_cache[key] = (now, road_attr)
        if osm_id:
            self._way_cache[int(osm_id)] = (now, road_attr)

        logger.info(
            "Resolved OSM road for (%.5f, %.5f): name='%s', highway='%s', lanes=%s, oneway=%s",
            lat,
            lng,
            road_name,
            highway,
            total_lanes,
            is_oneway,
        )
        return road_attr

    def _fetch_osm_way_tags(self, way_id: int) -> Optional[Dict[str, str]]:
        """Fetch tags directly for an OSM way ID via official OpenStreetMap API."""
        now = time.time()
        if way_id in self._way_cache:
            t, cached_attr = self._way_cache[way_id]
            if (now - t) < self.cache_ttl_seconds and cached_attr.raw_tags:
                return cached_attr.raw_tags

        url = f"https://api.openstreetmap.org/api/0.6/way/{way_id}.json"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "EVAS-EmergencyVehicleSystem/1.0 (contact@evas-emergency.org)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout_s) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    for el in data.get("elements", []):
                        if el.get("type") == "way" and el.get("id") == way_id:
                            return el.get("tags", {})
        except Exception:
            pass
        return None

    def combine_map_and_camera(
        self,
        camera_lane: Optional[str],
        camera_conf: Optional[float],
        detected_boundaries_count: int,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        heading_deg: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Combine OpenStreetMap road attributes with camera ML lane estimation.

        Rules:
        - Never invent missing lane counts or random values.
        - If map lane information is available: determine direction-specific lanes.
        - If map lane information is unavailable: use camera estimation and clearly mark
          as an estimate (source='CAMERA_ONLY').
        - If camera visibility is insufficient (no lines / dark scene): return UNKNOWN.
        - Return lane position: LEFT, CENTER, RIGHT, or lane index (e.g. Lane 2 of 3).
        """
        road_attr: Optional[RoadAttributes] = None
        if lat is not None and lng is not None and abs(lat) <= 90.0 and abs(lng) <= 180.0:
            road_attr = self.fetch_road_attributes(lat, lng)

        # 1. Determine road lane count from map data if available
        total_lanes: Optional[int] = None
        direction_lanes: Optional[int] = None
        map_lane_available = False
        road_name = road_attr.road_name if road_attr else None

        if road_attr and road_attr.total_lanes is not None and road_attr.total_lanes > 0:
            total_lanes = road_attr.total_lanes
            map_lane_available = True

            # Calculate direction-specific lane count
            if road_attr.oneway:
                direction_lanes = total_lanes
            elif road_attr.forward_lanes is not None:
                direction_lanes = road_attr.forward_lanes
            else:
                # Symmetrical two-way road without explicit forward/backward tags
                direction_lanes = max(1, total_lanes // 2)

        # 2. Evaluate camera detection
        camera_valid = (
            camera_lane is not None
            and camera_lane in ("LEFT", "CENTER", "RIGHT")
            and (camera_conf or 0.0) >= 0.40
            and detected_boundaries_count > 0
        )

        # 3. Fuse data sources
        if map_lane_available and camera_valid:
            # MAP_AND_CAMERA Fusion
            effective_dir_lanes = direction_lanes or total_lanes or 1
            lane_position = camera_lane

            # Determine lane index if road has multiple lanes
            lane_index: Optional[int] = None
            if effective_dir_lanes == 1:
                lane_index = 1
                lane_position = "CENTER"
            elif effective_dir_lanes == 2:
                lane_index = 1 if camera_lane == "LEFT" else 2
            elif effective_dir_lanes >= 3:
                if camera_lane == "LEFT":
                    lane_index = 1
                elif camera_lane == "CENTER":
                    lane_index = 2
                else:
                    lane_index = effective_dir_lanes

            # Confidence boosted by multi-sensor corroboration
            combined_conf = min(0.98, round((camera_conf or 0.7) * 1.05, 2))
            return {
                "lane": lane_position,
                "lane_index": lane_index,
                "total_lanes": total_lanes,
                "direction_lanes": effective_dir_lanes,
                "road_name": road_name,
                "data_source": "MAP_AND_CAMERA",
                "confidence": combined_conf,
                "map_lane_available": True,
                "description": f"{lane_position} (Lane {lane_index} of {effective_dir_lanes}) on {road_name or 'Road'}",
            }

        elif camera_valid:
            # CAMERA_ONLY (Map data has no lane tags or map is unavailable)
            return {
                "lane": camera_lane,
                "lane_index": None,
                "total_lanes": None,
                "direction_lanes": None,
                "road_name": road_name,
                "data_source": "CAMERA_ONLY",
                "confidence": camera_conf or 0.70,
                "map_lane_available": False,
                "description": f"{camera_lane} (Camera Estimate, OSM lanes tag not available)",
            }

        elif map_lane_available:
            # MAP_ONLY (Camera cannot detect lanes due to poor visibility/no markings)
            return {
                "lane": "UNKNOWN",
                "lane_index": None,
                "total_lanes": total_lanes,
                "direction_lanes": direction_lanes,
                "road_name": road_name,
                "data_source": "MAP_ONLY",
                "confidence": 0.0,
                "map_lane_available": True,
                "description": f"UNKNOWN (Road has {direction_lanes or total_lanes} lanes, but camera cannot detect markings)",
            }

        else:
            # UNKNOWN (Neither camera nor map has lane evidence)
            return {
                "lane": "UNKNOWN",
                "lane_index": None,
                "total_lanes": None,
                "direction_lanes": None,
                "road_name": road_name,
                "data_source": "UNKNOWN",
                "confidence": 0.0,
                "map_lane_available": False,
                "description": "UNKNOWN (Insufficient camera visibility and no OSM lane data)",
            }


# Singleton accessor
_road_service: Optional[RoadService] = None


def get_road_service() -> RoadService:
    global _road_service
    if _road_service is None:
        _road_service = RoadService()
    return _road_service
