"""
Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 1 — Backend Foundation + Real-Time Communication

matching_engine.py
==================
FUTURE VEHICLE-MATCHING INTELLIGENCE (STEP 2).

This module is intentionally a STUB in Step 1.

STEP 2 will implement the logic that decides WHICH participant vehicles
are in the path / corridor of the ambulance and therefore need a
targeted alert. The matching considers:

    - ambulance position, heading, speed
    - participant position, heading, speed
    - distance between ambulance and participant
    - ambulance route and route corridor (from route_engine)
    - lane / path information (from Step 3 AI lane detection)

The interface defined here is designed so that:

- The WebSocket handlers do NOT need to change when the real
  implementation is dropped in.
- The matching engine is REPLACEABLE: swap the concrete implementation
  by changing the factory call in main.py.

Public contract (STEP 2 will implement the bodies):
    match_vehicles(ambulance_state, vehicle_states, corridor) -> List[MatchResult]
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import List, Optional

from models import AmbulanceState, VehicleState
from route_engine import Corridor, RouteEngine, bearing_deg, haversine_distance_m

logger = logging.getLogger("backend.matching_engine")


@dataclass
class MatchingConfig:
    """Configurable thresholds for vehicle-ambulance matching.

    GPS ACCURACY NOTICE:
    Civilian L1 GPS (including NEO-6M and typical smartphones) has a typical
    horizontal error of 3 to 5 meters in open sky and 10+ meters in urban canyons.
    Standard highway and urban lanes are only 3.0 to 3.7 meters wide.
    Consequently, GPS coordinates ALONE cannot reliably determine which lane
    a vehicle occupies (e.g. Lane 1 vs Lane 2). Camera-based lane estimation
    (Step 8) is required for lane-level resolution.
    """

    max_search_radius_m: float = 600.0       # Ignore vehicles beyond this radius
    max_corridor_distance_m: float = 35.0     # Default road corridor half-width
    max_bearing_divergence_deg: float = 75.0  # Angle threshold to qualify as 'ahead'
    max_age_seconds: float = 20.0             # Telemetry freshness threshold
    min_speed_kmh_for_heading: float = 5.0    # Min speed before GPS heading is considered reliable


@dataclass
class MatchResult:
    """The result of matching ONE vehicle against the ambulance context.

    Attributes:
        vehicle_id: Identifier of the matched vehicle.
        in_corridor: Whether the vehicle lies inside the ambulance route corridor.
        distance_m: Straight-line distance from the ambulance to the vehicle (m).
        corridor_distance_m: Perpendicular distance from vehicle to route polyline (m).
        is_ahead: True if vehicle is ahead of the ambulance along its path.
        heading_aligned: True if vehicle heading matches direction of corridor.
        data_fresh: True if vehicle telemetry has not expired.
        time_to_encounter_s: Estimated seconds until ambulance reaches vehicle.
        should_alert: Relevance recommendation for warning the vehicle.
        relevance_score: Assessment score between 0.0 and 1.0.
        relevance_reason: Human-readable explanation of the assessment.
    """

    vehicle_id: str
    in_corridor: bool
    distance_m: float
    corridor_distance_m: float = 0.0
    is_ahead: bool = False
    heading_aligned: Optional[bool] = None
    data_fresh: bool = True
    time_to_encounter_s: Optional[float] = None
    should_alert: bool = False
    relevance_score: float = 0.0
    relevance_reason: str = ""
    vehicle_lane: Optional[str] = "UNKNOWN"
    ambulance_lane: str = "CENTER"
    lane_conflict: str = "NONE"  # DIRECT_BLOCKING, ADJACENT_CLEAR, UNKNOWN_CAUTION, NONE


class MatchingEngine:
    """Base interface for vehicle matching."""

    def match_vehicles(
        self,
        ambulance: AmbulanceState,
        vehicle_states: List[VehicleState],
        corridor: Optional[Corridor] = None,
        ambulance_lane: Optional[str] = None,
    ) -> List[MatchResult]:
        """Return one MatchResult per vehicle describing its relationship
        to the ambulance."""
        raise NotImplementedError("Subclasses must implement match_vehicles")


class DefaultMatchingEngine(MatchingEngine):
    """Production matching engine evaluating geometry, route corridor, heading,
    and freshness."""

    def __init__(self, config: Optional[MatchingConfig] = None) -> None:
        self.config = config or MatchingConfig()
        self._route_engine = RouteEngine()

    def _angle_diff_deg(self, angle1: float, angle2: float) -> float:
        """Calculate the absolute difference between two bearings in degrees [0, 180]."""
        diff = (angle1 - angle2 + 180.0) % 360.0 - 180.0
        return abs(diff)

    def match_vehicles(
        self,
        ambulance: AmbulanceState,
        vehicle_states: List[VehicleState],
        corridor: Optional[Corridor] = None,
        ambulance_lane: Optional[str] = None,
    ) -> List[MatchResult]:
        """Evaluate participant vehicles against ambulance telemetry, corridor, and camera lanes."""
        results: List[MatchResult] = []

        # Determine ambulance fixed designated lane
        target_amb_lane = (ambulance_lane or "CENTER").upper()
        try:
            from device_service import get_device_service
            amb_cfg = get_device_service().get_ambulance_config(ambulance.ambulance_id or "AMB01")
            target_amb_lane = amb_cfg.get("configured_lane", "CENTER").upper()
        except Exception:
            pass

        if not ambulance.emergency:
            # Ambulance is not in emergency mode; no vehicles need clearance
            for v in vehicle_states:
                results.append(
                    MatchResult(
                        vehicle_id=v.vehicle_id,
                        in_corridor=False,
                        distance_m=haversine_distance_m(ambulance.lat, ambulance.lng, v.lat, v.lng),
                        relevance_reason="Ambulance is not in emergency mode",
                        vehicle_lane=str(v.lane).upper() if v.lane else "UNKNOWN",
                        ambulance_lane=target_amb_lane,
                        lane_conflict="NONE",
                    )
                )
            return results

        # Ambulance motion parameters
        amb_has_heading = (
            ambulance.speed_kmh is not None
            and ambulance.speed_kmh >= self.config.min_speed_kmh_for_heading
            and ambulance.heading_deg is not None
        )
        amb_speed_ms = (ambulance.speed_kmh or 0.0) / 3.6

        for v in vehicle_states:
            # Skip if vehicle is the ambulance itself
            if v.vehicle_id == (ambulance.ambulance_id or "AMB01"):
                continue

            # 1. Freshness check
            is_fresh = not v.is_stale(max_age_seconds=self.config.max_age_seconds)
            dist_m = haversine_distance_m(ambulance.lat, ambulance.lng, v.lat, v.lng)

            # Resolve camera-detected vehicle lane
            v_lane_raw = str(v.lane).strip().upper() if v.lane else "UNKNOWN"
            if v_lane_raw in ("1", "LEFT"):
                veh_lane = "LEFT"
            elif v_lane_raw in ("2", "CENTER"):
                veh_lane = "CENTER"
            elif v_lane_raw in ("3", "RIGHT"):
                veh_lane = "RIGHT"
            else:
                veh_lane = "UNKNOWN"

            if not is_fresh:
                results.append(
                    MatchResult(
                        vehicle_id=v.vehicle_id,
                        in_corridor=False,
                        distance_m=dist_m,
                        data_fresh=False,
                        should_alert=False,
                        relevance_score=0.0,
                        relevance_reason="Telemetry is stale (>20s old) - ignored",
                        vehicle_lane=veh_lane,
                        ambulance_lane=target_amb_lane,
                        lane_conflict="NONE",
                    )
                )
                continue

            # 2. Distance pre-filter
            if dist_m > self.config.max_search_radius_m:
                results.append(
                    MatchResult(
                        vehicle_id=v.vehicle_id,
                        in_corridor=False,
                        distance_m=dist_m,
                        data_fresh=True,
                        should_alert=False,
                        relevance_score=0.0,
                        relevance_reason=f"Outside search radius ({dist_m:.0f}m > {self.config.max_search_radius_m}m)",
                        vehicle_lane=veh_lane,
                        ambulance_lane=target_amb_lane,
                        lane_conflict="NONE",
                    )
                )
                continue

            # 3. Ahead vs Behind determination
            bearing_to_veh = bearing_deg(ambulance.lat, ambulance.lng, v.lat, v.lng)
            is_ahead = True
            if amb_has_heading:
                angle_offset = self._angle_diff_deg(ambulance.heading_deg, bearing_to_veh)
                is_ahead = angle_offset <= self.config.max_bearing_divergence_deg

            # 4. Corridor containment
            in_corridor = False
            corridor_dist_m = 0.0
            if corridor is not None and corridor.route and corridor.route.points:
                corridor_dist_m = self._route_engine.distance_to_corridor_m(v.lat, v.lng, corridor)
                in_corridor = (corridor_dist_m <= corridor.width_m)
            else:
                in_corridor = is_ahead and (dist_m <= self.config.max_search_radius_m)
                corridor_dist_m = dist_m

            # 5. Heading alignment
            heading_aligned: Optional[bool] = None
            if (
                v.speed_kmh is not None
                and v.speed_kmh >= self.config.min_speed_kmh_for_heading
                and v.heading_deg is not None
                and amb_has_heading
            ):
                h_diff = self._angle_diff_deg(ambulance.heading_deg, v.heading_deg)
                heading_aligned = (h_diff <= 60.0)

            # 6. Time to encounter
            time_to_encounter_s = None
            if amb_speed_ms > 1.0 and is_ahead:
                time_to_encounter_s = round(dist_m / amb_speed_ms, 1)

            # 7. Lane-Aware Conflict Evaluation (PHASE 5)
            should_alert = False
            relevance_score = 0.0
            lane_conflict = "NONE"
            reason_parts = []

            if not is_ahead:
                reason_parts.append("Behind ambulance")
            elif not in_corridor:
                reason_parts.append(f"Outside route corridor ({corridor_dist_m:.1f}m from route)")
            else:
                dist_factor = max(0.0, 1.0 - (dist_m / self.config.max_search_radius_m))
                if veh_lane == target_amb_lane:
                    # DIRECT SAME-LANE CONFLICT
                    lane_conflict = "DIRECT_BLOCKING"
                    should_alert = True
                    relevance_score = round(0.70 + 0.30 * dist_factor, 2)
                    reason_parts.append(f"DIRECT CONFLICT: In ambulance lane ({target_amb_lane}) at {dist_m:.0f}m - EVACUATE LANE")
                elif veh_lane == "UNKNOWN":
                    # AMBIGUOUS / UNKNOWN LANE
                    lane_conflict = "UNKNOWN_CAUTION"
                    should_alert = True
                    relevance_score = round(0.45 + 0.45 * dist_factor, 2)
                    reason_parts.append(f"Ahead in corridor at {dist_m:.0f}m; lane UNKNOWN - caution advised")
                else:
                    # ADJACENT LANE (e.g. Left vs Center)
                    lane_conflict = "ADJACENT_CLEAR"
                    should_alert = False  # Vehicle does not block ambulance path
                    relevance_score = 0.25
                    reason_parts.append(f"Adjacent lane ({veh_lane}); ambulance in {target_amb_lane} - maintain course")

                if time_to_encounter_s is not None:
                    reason_parts.append(f"encounter in ~{time_to_encounter_s}s")

            results.append(
                MatchResult(
                    vehicle_id=v.vehicle_id,
                    in_corridor=in_corridor,
                    distance_m=round(dist_m, 1),
                    corridor_distance_m=round(corridor_dist_m, 1),
                    is_ahead=is_ahead,
                    heading_aligned=heading_aligned,
                    data_fresh=True,
                    time_to_encounter_s=time_to_encounter_s,
                    should_alert=should_alert,
                    relevance_score=relevance_score,
                    relevance_reason=", ".join(reason_parts),
                    vehicle_lane=veh_lane,
                    ambulance_lane=target_amb_lane,
                    lane_conflict=lane_conflict,
                )
            )

        return results


def create_default_matching_engine() -> MatchingEngine:
    """Factory used by main.py to build the matching engine."""
    return DefaultMatchingEngine()


def filter_by_distance(
    ambulance: AmbulanceState,
    vehicle_states: List[VehicleState],
    max_distance_m: float,
) -> List[VehicleState]:
    """Return only vehicles within `max_distance_m` of the ambulance."""
    out: List[VehicleState] = []
    for v in vehicle_states:
        d = haversine_distance_m(ambulance.lat, ambulance.lng, v.lat, v.lng)
        if d <= max_distance_m:
            out.append(v)
    return out