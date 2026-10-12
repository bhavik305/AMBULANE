"""Step 6 Vehicle Matching Engine Tests."""

import time

from models import AmbulanceState, VehicleState
from route_engine import Route, RoutePoint, RouteEngine
from matching_engine import DefaultMatchingEngine, MatchingConfig


def test_vehicle_matching_scenarios():
    now = time.time()
    route_engine = RouteEngine()
    matching_engine = DefaultMatchingEngine(
        MatchingConfig(
            max_search_radius_m=500.0,
            max_corridor_distance_m=30.0,
            max_bearing_divergence_deg=75.0,
            max_age_seconds=15.0,
        )
    )

    # Route: Heading North from (12.9700, 77.5900) to (12.9800, 77.5900)
    p_start = RoutePoint(lat=12.9700, lng=77.5900)
    p_end = RoutePoint(lat=12.9800, lng=77.5900)
    route = Route(points=[p_start, p_end], distance_m=1111.0, duration_s=100.0, source="test")
    corridor = route_engine.get_route_corridor(route, corridor_width_m=30.0)

    # Ambulance at (12.9720, 77.5900), traveling North (heading=0 deg, speed=54 km/h = 15 m/s)
    amb = AmbulanceState(
        lat=12.9720,
        lng=77.5900,
        speed_kmh=54.0,
        heading_deg=0.0,
        emergency=True,
        ts=now,
        received_at=now,
    )

    # Vehicle 1: Ahead by ~220m along the corridor (at 12.9740, 77.5900)
    v1_ahead_in_corridor = VehicleState(
        vehicle_id="veh_ahead_in_corridor",
        lat=12.9740,
        lng=77.5900,
        speed_kmh=40.0,
        heading_deg=0.0,
        ts=now,
        received_at=now,
    )

    # Vehicle 2: Behind the ambulance (at 12.9710, 77.5900, ~110m South)
    v2_behind = VehicleState(
        vehicle_id="veh_behind",
        lat=12.9710,
        lng=77.5900,
        speed_kmh=35.0,
        heading_deg=0.0,
        ts=now,
        received_at=now,
    )

    # Vehicle 3: Ahead in latitude, but on a parallel road 150m to the East (77.5900 + ~0.0014)
    v3_off_corridor = VehicleState(
        vehicle_id="veh_parallel_street",
        lat=12.9740,
        lng=77.5914,
        speed_kmh=40.0,
        heading_deg=0.0,
        ts=now,
        received_at=now,
    )

    # Vehicle 4: Ahead in corridor, but telemetry is 45 seconds old (stale)
    v4_stale = VehicleState(
        vehicle_id="veh_stale",
        lat=12.9730,
        lng=77.5900,
        speed_kmh=30.0,
        heading_deg=0.0,
        ts=now - 45.0,
        received_at=now - 45.0,
    )

    vehicles = [v1_ahead_in_corridor, v2_behind, v3_off_corridor, v4_stale]
    results = matching_engine.match_vehicles(amb, vehicles, corridor=corridor)
    res_map = {r.vehicle_id: r for r in results}

    # Verify Vehicle 1 (Ahead & in corridor)
    r1 = res_map["veh_ahead_in_corridor"]
    assert r1.is_ahead is True
    assert r1.in_corridor is True
    assert r1.should_alert is True
    assert r1.time_to_encounter_s is not None
    assert r1.relevance_score > 0.6
    print("V1 Result (Ahead in corridor):", r1)

    # Verify Vehicle 2 (Behind) -> Must NOT alert despite close straight-line proximity!
    r2 = res_map["veh_behind"]
    assert r2.is_ahead is False
    assert r2.should_alert is False
    assert "Behind ambulance" in r2.relevance_reason
    print("V2 Result (Behind ambulance):", r2)

    # Verify Vehicle 3 (Off corridor on parallel street) -> Must NOT alert!
    r3 = res_map["veh_parallel_street"]
    assert r3.in_corridor is False
    assert r3.should_alert is False
    assert "Outside route corridor" in r3.relevance_reason
    print("V3 Result (Off corridor parallel street):", r3)

    # Verify Vehicle 4 (Stale) -> Must NOT alert!
    r4 = res_map["veh_stale"]
    assert r4.data_fresh is False
    assert r4.should_alert is False
    assert "stale" in r4.relevance_reason
    print("V4 Result (Stale telemetry):", r4)


def test_non_emergency_mode():
    now = time.time()
    matching_engine = DefaultMatchingEngine()
    amb_non_emg = AmbulanceState(
        lat=12.9720,
        lng=77.5900,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=False,  # Emergency is OFF
        ts=now,
        received_at=now,
    )
    v = VehicleState(
        vehicle_id="veh_test",
        lat=12.9730,
        lng=77.5900,
        ts=now,
        received_at=now,
    )
    results = matching_engine.match_vehicles(amb_non_emg, [v])
    assert len(results) == 1
    assert results[0].should_alert is False
    assert "not in emergency mode" in results[0].relevance_reason


if __name__ == "__main__":
    test_vehicle_matching_scenarios()
    test_non_emergency_mode()
    print("STEP 6 Matching Engine tests PASSED successfully!")
