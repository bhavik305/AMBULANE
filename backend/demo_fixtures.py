"""Lane-Aware Intelligent Emergency Vehicle Alert System
PHASE 8: Honest Demonstration Mode & Deterministic Scenarios.

Strict Non-Fabrication Rules:
- All scenario inputs are strictly deterministic and documented.
- Explicitly labelled data_mode="TEST_DATA_SIMULATED".
- Never mixed silently with live hardware telemetry.
- Zero random number generation for coordinates, lanes, or signal aspects.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from models import AmbulanceState, VehicleState
from websocket_manager import get_ws_manager
from device_service import get_device_service, DeviceRole, DeviceRegisterRequest
from junction_service import get_junction_service
from dispatch_service import dispatch_alerts_and_fleet

logger = logging.getLogger("backend.demo_fixtures")

# Deterministic Bangalore Demonstration Corridor Coordinates (MG Road)
CORRIDOR_LAT = 12.9710
CORRIDOR_LNG = 77.5950
JUNC_LAT = 12.9740
JUNC_LNG = 77.5950


def list_demo_scenarios() -> list[Dict[str, Any]]:
    """Return catalog of available deterministic demonstration scenarios."""
    return [
        {"id": "DIRECT_BLOCKING", "name": "Direct Lane Blocking (Ambulance & Vehicle in Center Lane 2)"},
        {"id": "ADJACENT_CLEAR", "name": "Adjacent Clear Lane (Ambulance Center L2, Vehicle Left L1)"},
        {"id": "UNKNOWN_LANE", "name": "Unknown Lane / Low Confidence (Conf < 0.45)"},
        {"id": "ETA_SIGNAL_PREEMPTION", "name": "ETA Signal Preemption (ETA <= 30s triggers JUNC_01 clearance)"},
        {"id": "STALE_TELEMETRY", "name": "Stale Telemetry Suppression (GPS age > 20s blocks priority)"},
    ]


async def load_deterministic_scenario(scenario_id: str) -> Dict[str, Any]:
    """Load and execute a documented, deterministic demonstration scenario."""
    ws_mgr = get_ws_manager()
    dev_svc = get_device_service()
    junc_svc = get_junction_service()
    now = time.time()

    # Ensure devices are registered with appropriate roles
    dev_svc.register_device(
        DeviceRegisterRequest(
            device_id="AMB01",
            role=DeviceRole.AMBULANCE,
            admin_pin="9911",
            configured_lane="CENTER",
            configured_approach="NORTH_SOUTH",
        )
    )
    dev_svc.register_device(
        DeviceRegisterRequest(
            device_id="V001",
            role=DeviceRole.NORMAL_VEHICLE,
            configured_lane=None,
        )
    )

    if scenario_id == "DIRECT_BLOCKING":
        # Scenario 1: Ambulance in Center, Vehicle in Center at 180m ahead -> Direct Conflict
        amb = AmbulanceState(
            ambulance_id="AMB01",
            lat=CORRIDOR_LAT,
            lng=CORRIDOR_LNG,
            speed_kmh=50.0,
            heading_deg=0.0,
            emergency=True,
            ts=now,
            received_at=now,
        )
        veh = VehicleState(
            vehicle_id="V001",
            lat=CORRIDOR_LAT + 0.0016,  # ~178m ahead north
            lng=CORRIDOR_LNG,
            speed_kmh=40.0,
            heading_deg=0.0,
            lane="CENTER",
            lane_confidence=0.92,
            ts=now,
            received_at=now,
        )
        ws_mgr.set_ambulance_state(amb)
        ws_mgr.set_vehicle_state("V001", veh)
        await dispatch_alerts_and_fleet()

        return {
            "status": "ok",
            "scenario_id": "DIRECT_BLOCKING",
            "title": "Scenario 1: Direct Same-Lane Conflict",
            "data_mode": "TEST_DATA_SIMULATED",
            "description": "Ambulance in designated CENTER lane; Vehicle V001 ahead in CENTER lane at 178m.",
            "expected_outcome": "High-priority EVACUATE LANE alert delivered to V001 (Conflict: DIRECT_BLOCKING).",
            "ambulance_lane": "CENTER",
            "vehicle_lane": "CENTER",
            "distance_m": 178.0,
            "timestamp": now,
        }

    elif scenario_id == "ADJACENT_CLEAR":
        # Scenario 2: Ambulance in Center, Vehicle in Left Lane at 150m ahead -> Adjacent Safe Pass
        amb = AmbulanceState(
            ambulance_id="AMB01",
            lat=CORRIDOR_LAT,
            lng=CORRIDOR_LNG,
            speed_kmh=50.0,
            heading_deg=0.0,
            emergency=True,
            ts=now,
            received_at=now,
        )
        veh = VehicleState(
            vehicle_id="V001",
            lat=CORRIDOR_LAT + 0.00135,  # ~150m ahead north
            lng=CORRIDOR_LNG,
            speed_kmh=42.0,
            heading_deg=0.0,
            lane="LEFT",
            lane_confidence=0.88,
            ts=now,
            received_at=now,
        )
        ws_mgr.set_ambulance_state(amb)
        ws_mgr.set_vehicle_state("V001", veh)
        await dispatch_alerts_and_fleet()

        return {
            "status": "ok",
            "scenario_id": "ADJACENT_CLEAR",
            "title": "Scenario 2: Adjacent Lane Clearance",
            "data_mode": "TEST_DATA_SIMULATED",
            "description": "Ambulance in designated CENTER lane; Vehicle V001 ahead in LEFT lane at 150m.",
            "expected_outcome": "Informational advisory to V001 (Conflict: ADJACENT_CLEAR). No emergency evacuation required.",
            "ambulance_lane": "CENTER",
            "vehicle_lane": "LEFT",
            "distance_m": 150.0,
            "timestamp": now,
        }

    elif scenario_id == "UNKNOWN_LANE":
        # Scenario 3: Camera Lane is Ambiguous / UNKNOWN -> Caution Alert
        amb = AmbulanceState(
            ambulance_id="AMB01",
            lat=CORRIDOR_LAT,
            lng=CORRIDOR_LNG,
            speed_kmh=50.0,
            heading_deg=0.0,
            emergency=True,
            ts=now,
            received_at=now,
        )
        veh = VehicleState(
            vehicle_id="V001",
            lat=CORRIDOR_LAT + 0.0015,  # ~165m ahead north
            lng=CORRIDOR_LNG,
            speed_kmh=38.0,
            heading_deg=0.0,
            lane="UNKNOWN",
            lane_confidence=0.32,
            ts=now,
            received_at=now,
        )
        ws_mgr.set_ambulance_state(amb)
        ws_mgr.set_vehicle_state("V001", veh)
        await dispatch_alerts_and_fleet()

        return {
            "status": "ok",
            "scenario_id": "UNKNOWN_LANE",
            "title": "Scenario 3: Ambiguous / Occluded Camera Lane",
            "data_mode": "TEST_DATA_SIMULATED",
            "description": "Ambulance in designated CENTER lane; Vehicle V001 camera markings occluded (UNKNOWN lane).",
            "expected_outcome": "Caution advisory delivered to V001 (Conflict: UNKNOWN_CAUTION).",
            "ambulance_lane": "CENTER",
            "vehicle_lane": "UNKNOWN",
            "distance_m": 165.0,
            "timestamp": now,
        }

    elif scenario_id == "ETA_SIGNAL_PREEMPTION":
        # Scenario 4: Ambulance approaching JUNC_01 within ETA trigger threshold (23s ETA)
        amb = AmbulanceState(
            ambulance_id="AMB01",
            lat=JUNC_LAT - 0.00288,  # ~320m south of intersection
            lng=JUNC_LNG,
            speed_kmh=50.0,
            heading_deg=0.0,
            emergency=True,
            ts=now,
            received_at=now,
        )
        ws_mgr.set_ambulance_state(amb)
        await junc_svc.evaluate_eta_and_trigger(amb)
        junc_state = junc_svc.get_state("JUNC_01")

        return {
            "status": "ok",
            "scenario_id": "ETA_SIGNAL_PREEMPTION",
            "title": "Scenario 4: ETA-Triggered Traffic Signal Preemption",
            "data_mode": "TEST_DATA_SIMULATED",
            "description": "Ambulance 320m south of JUNC_01 at 50 km/h (ETA ~23s <= 30s threshold).",
            "expected_outcome": "Priority sequence initiated: Approach B Yellow -> All-Red -> Approach A Green.",
            "junction_id": "JUNC_01",
            "junction_state": junc_state.model_dump() if junc_state else {},
            "timestamp": now,
        }

    elif scenario_id == "STALE_TELEMETRY":
        # Scenario 5: Stale GPS (>20s old) -> Priority Suppressed
        stale_ts = now - 45.0
        amb = AmbulanceState(
            ambulance_id="AMB01",
            lat=JUNC_LAT - 0.002,
            lng=JUNC_LNG,
            speed_kmh=50.0,
            heading_deg=0.0,
            emergency=True,
            ts=stale_ts,
            received_at=stale_ts,
        )
        ws_mgr.set_ambulance_state(amb)
        await junc_svc.evaluate_eta_and_trigger(amb)
        junc_state = junc_svc.get_state("JUNC_01")

        return {
            "status": "ok",
            "scenario_id": "STALE_TELEMETRY",
            "title": "Scenario 5: Stale Telemetry Safety Suppression",
            "data_mode": "TEST_DATA_SIMULATED",
            "description": "Ambulance GPS data is 45 seconds old (stale threshold = 20s).",
            "expected_outcome": "Signal priority request suppressed and active vehicle alerts cleared for safety.",
            "is_stale": True,
            "junction_state": junc_state.model_dump() if junc_state else {},
            "timestamp": now,
        }

    else:
        return {
            "status": "error",
            "message": f"Unknown scenario_id '{scenario_id}'. Available: DIRECT_BLOCKING, ADJACENT_CLEAR, UNKNOWN_LANE, ETA_SIGNAL_PREEMPTION, STALE_TELEMETRY",
        }
