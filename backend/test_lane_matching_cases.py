"""Lane-Aware Intelligent Emergency Vehicle Alert System
PHASE 5 & PHASE 8: Comprehensive Lane-Aware Vehicle Matching and Journey Edge Case Tests.

Tests:
1. Vehicle ahead in corridor (DIRECT_BLOCKING when in ambulance lane).
2. Vehicle ahead in corridor (ADJACENT_CLEAR when in distinct lane).
3. Vehicle ahead in corridor with unavailable or low-confidence camera data (UNKNOWN_CAUTION).
4. Vehicle behind the ambulance (no alert, is_ahead=False).
5. Vehicle traveling in the opposite direction (heading divergence > 75 deg, no alert).
6. Vehicle on a nearby but unrelated road (outside corridor width, no alert).
7. Vehicle with stale GPS telemetry (> 20s old, alert suppressed, marked stale).
8. Ambulance with missing or invalid GPS coordinates (handled safely, returns empty matches).
9. Active emergency journey lifecycle: start journey, store route corridor, stop journey.
10. Device registration & role authorization (prevent accidental simultaneous dual roles).
"""

import time
import pytest
from fastapi.testclient import TestClient

from main import app
from models import (
    AmbulanceState,
    DeviceRegisterRequest,
    DeviceRole,
    StartJourneyRequest,
    StopJourneyRequest,
    VehicleState,
)
from matching_engine import DefaultMatchingEngine, MatchingConfig
from route_engine import Corridor, Route, RouteEngine, RoutePoint
from journey_service import get_journey_service
from device_service import get_device_service


client = TestClient(app)


# ---------------------------------------------------------------------------
# Test Case 1: Vehicle ahead in corridor with same lane (DIRECT_BLOCKING)
# ---------------------------------------------------------------------------
def test_vehicle_ahead_in_corridor_direct_blocking():
    now = time.time()
    engine = DefaultMatchingEngine()

    amb = AmbulanceState(
        lat=12.9716,
        lng=77.5946,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
        ambulance_id="AMB01",
    )

    v_ahead_same = VehicleState(
        vehicle_id="V_AHEAD_CEN",
        lat=12.9735,
        lng=77.5946,
        speed_kmh=35.0,
        heading_deg=0.0,
        lane="CENTER",
        lane_confidence=0.92,
        ts=now,
        received_at=now,
    )

    results = engine.match_vehicles(amb, [v_ahead_same], ambulance_lane="CENTER")
    assert len(results) == 1
    res = results[0]
    assert res.is_ahead is True
    assert res.should_alert is True
    assert res.lane_conflict == "DIRECT_BLOCKING"
    assert "EVACUATE LANE" in res.relevance_reason


# ---------------------------------------------------------------------------
# Test Case 2: Vehicle ahead in adjacent clear lane (ADJACENT_CLEAR)
# ---------------------------------------------------------------------------
def test_vehicle_ahead_in_adjacent_lane_clear():
    now = time.time()
    engine = DefaultMatchingEngine()

    amb = AmbulanceState(
        lat=12.9716,
        lng=77.5946,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
        ambulance_id="AMB01",
    )

    v_adjacent = VehicleState(
        vehicle_id="V_ADJACENT_LFT",
        lat=12.9735,
        lng=77.5946,
        speed_kmh=35.0,
        heading_deg=0.0,
        lane="LEFT",
        lane_confidence=0.88,
        ts=now,
        received_at=now,
    )

    results = engine.match_vehicles(amb, [v_adjacent], ambulance_lane="CENTER")
    assert len(results) == 1
    res = results[0]
    assert res.is_ahead is True
    assert res.should_alert is False  # Vehicle in adjacent lane does not block ambulance
    assert res.lane_conflict == "ADJACENT_CLEAR"
    assert "maintain course" in res.relevance_reason


# ---------------------------------------------------------------------------
# Test Case 3: Vehicle ahead with unavailable/low-confidence camera data
# ---------------------------------------------------------------------------
def test_vehicle_ahead_with_unknown_or_low_confidence_lane():
    now = time.time()
    engine = DefaultMatchingEngine()

    amb = AmbulanceState(
        lat=12.9716,
        lng=77.5946,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
        ambulance_id="AMB01",
    )

    # Low camera confidence (< 0.50) must not be trusted as physical lane
    v_low_conf = VehicleState(
        vehicle_id="V_LOW_CONF",
        lat=12.9735,
        lng=77.5946,
        speed_kmh=35.0,
        heading_deg=0.0,
        lane="CENTER",
        lane_confidence=0.32,  # Low confidence
        ts=now,
        received_at=now,
    )

    results = engine.match_vehicles(amb, [v_low_conf], ambulance_lane="CENTER")
    assert len(results) == 1
    res = results[0]
    assert res.vehicle_lane == "UNKNOWN"
    assert res.lane_conflict == "UNKNOWN_CAUTION"
    assert res.should_alert is True  # Caution alert issued
    assert "caution advised" in res.relevance_reason


# ---------------------------------------------------------------------------
# Test Case 4: Vehicle behind the ambulance
# ---------------------------------------------------------------------------
def test_vehicle_behind_ambulance_no_alert():
    now = time.time()
    engine = DefaultMatchingEngine()

    # Ambulance moving North (heading 0 deg) at lat 12.9730
    amb = AmbulanceState(
        lat=12.9730,
        lng=77.5946,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
        ambulance_id="AMB01",
    )

    # Vehicle is located South of the ambulance at lat 12.9710 (behind)
    v_behind = VehicleState(
        vehicle_id="V_BEHIND",
        lat=12.9710,
        lng=77.5946,
        speed_kmh=40.0,
        heading_deg=0.0,
        lane="CENTER",
        ts=now,
        received_at=now,
    )

    results = engine.match_vehicles(amb, [v_behind], ambulance_lane="CENTER")
    assert len(results) == 1
    res = results[0]
    assert res.is_ahead is False
    assert res.should_alert is False
    assert "Behind ambulance" in res.relevance_reason


# ---------------------------------------------------------------------------
# Test Case 5: Vehicle traveling in opposite direction
# ---------------------------------------------------------------------------
def test_vehicle_opposite_direction_traffic():
    now = time.time()
    engine = DefaultMatchingEngine()

    # Ambulance moving North (heading 0 deg)
    amb = AmbulanceState(
        lat=12.9716,
        lng=77.5946,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
        ambulance_id="AMB01",
    )

    # Vehicle ahead at lat 12.9735, but traveling South (heading 180 deg)
    v_oncoming = VehicleState(
        vehicle_id="V_ONCOMING",
        lat=12.9735,
        lng=77.5946,
        speed_kmh=45.0,
        heading_deg=180.0,  # Opposite direction!
        lane="CENTER",
        ts=now,
        received_at=now,
    )

    results = engine.match_vehicles(amb, [v_oncoming], ambulance_lane="CENTER")
    assert len(results) == 1
    res = results[0]
    assert res.heading_aligned is False
    assert res.lane_conflict == "OPPOSITE_DIRECTION"
    assert res.should_alert is False
    assert "opposite direction" in res.relevance_reason


# ---------------------------------------------------------------------------
# Test Case 6: Vehicle on nearby but unrelated road (outside corridor)
# ---------------------------------------------------------------------------
def test_vehicle_outside_corridor_on_parallel_street():
    now = time.time()
    engine = DefaultMatchingEngine()
    route_engine = RouteEngine()

    # Ambulance route corridor along longitude 77.5946
    route = Route(
        points=[
            RoutePoint(lat=12.9710, lng=77.5946),
            RoutePoint(lat=12.9750, lng=77.5946),
        ],
        distance_m=444.0,
    )
    corridor = route_engine.get_route_corridor(route, corridor_width_m=35.0)

    amb = AmbulanceState(
        lat=12.9710,
        lng=77.5946,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
        ambulance_id="AMB01",
    )

    # Vehicle is on parallel street 100 meters East (outside 35m corridor width)
    # Longitude offset ~0.001 deg is ~110 meters
    v_parallel = VehicleState(
        vehicle_id="V_PARALLEL",
        lat=12.9730,
        lng=77.5958,  # ~130m away laterally
        speed_kmh=40.0,
        heading_deg=0.0,
        lane="CENTER",
        ts=now,
        received_at=now,
    )

    results = engine.match_vehicles(amb, [v_parallel], corridor=corridor, ambulance_lane="CENTER")
    assert len(results) == 1
    res = results[0]
    assert res.in_corridor is False
    assert res.corridor_distance_m > 35.0
    assert res.should_alert is False
    assert "Outside route corridor" in res.relevance_reason


# ---------------------------------------------------------------------------
# Test Case 7: Vehicle with stale GPS telemetry (> 20s old)
# ---------------------------------------------------------------------------
def test_vehicle_stale_telemetry_suppressed():
    now = time.time()
    engine = DefaultMatchingEngine()

    amb = AmbulanceState(
        lat=12.9716,
        lng=77.5946,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
        ambulance_id="AMB01",
    )

    # Telemetry is 35 seconds old
    v_stale = VehicleState(
        vehicle_id="V_STALE",
        lat=12.9730,
        lng=77.5946,
        speed_kmh=30.0,
        heading_deg=0.0,
        lane="CENTER",
        ts=now - 35.0,
        received_at=now - 35.0,
    )

    results = engine.match_vehicles(amb, [v_stale], ambulance_lane="CENTER")
    assert len(results) == 1
    res = results[0]
    assert res.data_fresh is False
    assert res.should_alert is False
    assert "stale" in res.relevance_reason.lower()


# ---------------------------------------------------------------------------
# Test Case 8: Ambulance with missing or invalid GPS coordinates
# ---------------------------------------------------------------------------
def test_ambulance_invalid_coordinates_handled_safely():
    now = time.time()
    engine = DefaultMatchingEngine()

    # Invalid lat/lng coordinates (e.g. 0,0 null island or out of range)
    amb_invalid = AmbulanceState(
        lat=0.0,
        lng=0.0,
        speed_kmh=0.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
        ambulance_id="AMB01",
    )

    v = VehicleState(
        vehicle_id="V_TEST",
        lat=12.9730,
        lng=77.5946,
        speed_kmh=30.0,
        heading_deg=0.0,
        lane="CENTER",
        ts=now,
        received_at=now,
    )

    results = engine.match_vehicles(amb_invalid, [v], ambulance_lane="CENTER")
    assert results == []


# ---------------------------------------------------------------------------
# Test Case 9: Active Emergency Journey Lifecycle (Start & Stop REST API)
# ---------------------------------------------------------------------------
def test_journey_lifecycle_and_api():
    j_svc = get_journey_service()

    # Clean any prior state
    j_svc.stop_journey(StopJourneyRequest(ambulance_id="AMB01"))

    # Initial check: no active journey
    resp_init = client.get("/api/journey/active")
    assert resp_init.status_code == 200
    assert resp_init.json()["active"] is False

    # Start emergency journey via REST endpoint
    start_payload = {
        "ambulance_id": "AMB01",
        "origin_name": "Manipal Hospital",
        "origin_lat": 12.9592,
        "origin_lng": 77.6534,
        "destination_name": "Victoria Hospital Trauma Care",
        "destination_lat": 12.9620,
        "destination_lng": 77.5740,
        "route_points": [
            {"lat": 12.9592, "lng": 77.6534},
            {"lat": 12.9605, "lng": 77.6100},
            {"lat": 12.9620, "lng": 77.5740},
        ],
        "distance_meters": 8200.0,
        "duration_seconds": 960.0,
        "assigned_lane": "LEFT",
        "admin_pin": "9911",
    }
    resp_start = client.post("/api/journey/start", json=start_payload)
    assert resp_start.status_code == 200
    data = resp_start.json()
    assert data["is_active"] is True
    assert data["assigned_lane"] == "LEFT"
    assert len(data["route_points"]) == 3

    # Verify active query returns the journey
    resp_active = client.get("/api/journey/active")
    assert resp_active.status_code == 200
    active_data = resp_active.json()
    assert active_data["active"] is True
    assert active_data["journey"]["origin_name"] == "Manipal Hospital"

    # Stop journey via REST endpoint
    resp_stop = client.post("/api/journey/stop", json={"ambulance_id": "AMB01"})
    assert resp_stop.status_code == 200
    assert resp_stop.json()["status"] == "stopped"

    # Check journey is no longer active
    resp_post_stop = client.get("/api/journey/active")
    assert resp_post_stop.json()["active"] is False


# ---------------------------------------------------------------------------
# Test Case 10: Device Registration & Simultaneous Role Protection
# ---------------------------------------------------------------------------
def test_device_registration_role_protection():
    dev_svc = get_device_service()

    # Normal vehicle registration
    reg_v = dev_svc.register_device(
        DeviceRegisterRequest(device_id="PHONE_DEV_01", role=DeviceRole.NORMAL_VEHICLE)
    )
    assert reg_v.role == DeviceRole.NORMAL_VEHICLE
    assert reg_v.auth_token.startswith("TOKEN_NOR_")

    # Attempting to register as AMBULANCE without correct PIN fails with 403
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        dev_svc.register_device(
            DeviceRegisterRequest(
                device_id="PHONE_DEV_01",
                role=DeviceRole.AMBULANCE,
                admin_pin="WRONG_PIN",
            )
        )
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Test Case 11: GET /api/config Endpoint (LAN IP, WS URL, Maps Config)
# ---------------------------------------------------------------------------
def test_api_config_endpoint():
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "lan_ip" in data
    assert "default_ws_url" in data
    assert data["map_provider"] == "openstreetmap"
    assert "tile.openstreetmap.org" in data["tile_url"]
    assert "OpenStreetMap" in data["attribution"]
    assert data["routing_service"] == "osrm"

