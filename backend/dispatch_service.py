"""
Real-time emergency alert and fleet dispatch service.
Integrates matching_engine with WebSocketManager to deliver targeted alerts.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from websocket_manager import get_ws_manager
from matching_engine import create_default_matching_engine, MatchingEngine

logger = logging.getLogger("backend.dispatch_service")

_matching_engine: Optional[MatchingEngine] = None


def get_matching_engine() -> MatchingEngine:
    global _matching_engine
    if _matching_engine is None:
        _matching_engine = create_default_matching_engine()
    return _matching_engine


def _parse_lane(lane_val: Any) -> int:
    """Normalize lane value to 1 (left), 2 (center), or 3 (right)."""
    if lane_val is None:
        return 2
    s = str(lane_val).strip().upper()
    if s in ("1", "LEFT"):
        return 1
    if s in ("3", "RIGHT"):
        return 3
    return 2


async def dispatch_alerts_and_fleet(corridor=None) -> None:
    """Evaluate current ambulance & vehicles state and push alerts / fleet updates."""
    ws_mgr = get_ws_manager()
    amb = ws_mgr.ambulance_state
    now = time.time()

    # Resolve active journey and corridor
    active_journey_data = None
    try:
        from journey_service import get_journey_service
        j_svc = get_journey_service()
        active_j = j_svc.get_active_journey()
        if active_j:
            active_journey_data = active_j.model_dump()
        if corridor is None:
            corridor = j_svc.get_active_corridor()
    except Exception:
        pass

    vehicles = list(ws_mgr.all_vehicle_states().values())

    from junction_service import get_junction_service
    junc_svc = get_junction_service()
    if amb is not None:
        await junc_svc.evaluate_eta_and_trigger(amb)
    junctions_data = junc_svc.get_all_states()

    amb_lane_label = "CENTER"
    amb_lane_num = 2
    amb_payload = None

    if amb is not None:
        try:
            from device_service import get_device_service
            amb_cfg = get_device_service().get_ambulance_config(amb.ambulance_id or "AMB01")
            amb_lane_label = amb_cfg.get("configured_lane", "CENTER").upper()
        except Exception:
            pass
        amb_lane_num = 1 if amb_lane_label == "LEFT" else (3 if amb_lane_label == "RIGHT" else 2)
        amb_payload = {
            "id": amb.ambulance_id or "AMB01",
            "lat": amb.lat,
            "lng": amb.lng,
            "speed_kmh": amb.speed_kmh,
            "heading_deg": amb.heading_deg,
            "emergency": amb.emergency,
            "lane": amb_lane_num,
            "lane_label": amb_lane_label,
        }

    # 1. Dispatch fleet update for Live Map, Fleet monitoring & Traffic Signals
    fleet_payload = {
        "type": "fleet_update",
        "timestamp": now,
        "ambulance": amb_payload,
        "active_journey": active_journey_data,
        "vehicles": {
            v.vehicle_id: {
                "id": v.vehicle_id,
                "lat": v.lat,
                "lng": v.lng,
                "speed_kmh": v.speed_kmh or 0.0,
                "heading_deg": v.heading_deg or 0.0,
                "lane": _parse_lane(v.lane),
                "lane_label": str(v.lane).upper() if v.lane else "UNKNOWN",
            }
            for v in vehicles
        },
        "junctions": junctions_data,
    }
    await ws_mgr.broadcast(fleet_payload)

    if amb is None or not vehicles:
        return


    # 2. Evaluate matches via matching engine
    engine = get_matching_engine()
    matches = engine.match_vehicles(amb, vehicles, corridor=corridor, ambulance_lane=amb_lane_label)

    for match in matches:
        v_state = ws_mgr.get_vehicle_state(match.vehicle_id)
        if v_state is None:
            continue

        if amb.emergency and match.should_alert:
            eta = match.time_to_encounter_s
            if eta is None or eta <= 0:
                speed_ms = max(2.0, (amb.speed_kmh or 50.0) / 3.6)
                eta = round(match.distance_m / speed_ms, 1)

            if match.lane_conflict == "DIRECT_BLOCKING":
                msg_code = "AMBULANCE_APPROACHING_DIRECT_LANE_CONFLICT"
                human_msg = f"CRITICAL: Emergency vehicle approaching in your lane ({match.ambulance_lane})! Safely clear the lane."
            else:
                msg_code = "AMBULANCE_APPROACHING_LANE_UNKNOWN"
                human_msg = f"CAUTION: Emergency vehicle approaching in corridor at {match.distance_m:.0f}m. Lane unconfirmed - stay alert."

            alert_payload = {
                "type": "emergency_alert",
                "to_id": match.vehicle_id,
                "ambulance_id": amb.ambulance_id or "AMB01",
                "ambulance_lat": amb.lat,
                "ambulance_lon": amb.lng,
                "distance": match.distance_m,
                "eta": int(eta),
                "emergency_state": True,
                "message_code": msg_code,
                "human_message": human_msg,
                "ambulance_lane": amb_lane_num,
                "ambulance_lane_label": match.ambulance_lane,
                "vehicle_lane": match.vehicle_lane,
                "lane_conflict": match.lane_conflict,
                "relevance_score": match.relevance_score,
                "relevance_reason": match.relevance_reason,
                "timestamp": now,
            }
            await ws_mgr.send_to_vehicle(match.vehicle_id, alert_payload)
            logger.info(
                "Alert dispatched to vehicle %s (dist=%.1fm, conflict=%s)",
                match.vehicle_id,
                match.distance_m,
                match.lane_conflict,
            )
        else:
            # Send clearance or adjacent lane status update
            clear_payload = {
                "type": "emergency_clear",
                "to_id": match.vehicle_id,
                "emergency_state": False,
                "message": match.relevance_reason or "Path is clear. Normal driving.",
                "ambulance_lane": amb_lane_num,
                "ambulance_lane_label": match.ambulance_lane,
                "vehicle_lane": match.vehicle_lane,
                "lane_conflict": match.lane_conflict,
                "distance": match.distance_m,
                "timestamp": now,
            }
            await ws_mgr.send_to_vehicle(match.vehicle_id, clear_payload)
