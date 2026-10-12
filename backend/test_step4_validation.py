"""Step 4 State Management and Validation Tests."""

import time
import pytest
from pydantic import ValidationError
from models import AmbulanceTelemetry, AmbulanceState, VehicleTelemetry, VehicleState
from websocket_manager import WebSocketManager


def test_ambulance_telemetry_valid():
    t = AmbulanceTelemetry(
        lat=12.9716,
        lng=77.5946,
        speed_kmh=45.0,
        heading_deg=90.0,
        emergency=True,
        ts=time.time(),
    )
    assert t.lat == 12.9716
    assert t.lng == 77.5946


def test_ambulance_telemetry_coordinate_out_of_range():
    # Lat > 90
    with pytest.raises(ValidationError):
        AmbulanceTelemetry(
            lat=95.0,
            lng=77.5946,
            speed_kmh=45.0,
            heading_deg=90.0,
            emergency=True,
            ts=time.time(),
        )
    # Lat < -90
    with pytest.raises(ValidationError):
        AmbulanceTelemetry(
            lat=-95.0,
            lng=77.5946,
            speed_kmh=45.0,
            heading_deg=90.0,
            emergency=True,
            ts=time.time(),
        )
    # Lng > 180
    with pytest.raises(ValidationError):
        AmbulanceTelemetry(
            lat=12.0,
            lng=185.0,
            speed_kmh=45.0,
            heading_deg=90.0,
            emergency=True,
            ts=time.time(),
        )


def test_ambulance_telemetry_invalid_speed_and_heading():
    # Negative speed
    with pytest.raises(ValidationError):
        AmbulanceTelemetry(
            lat=12.0,
            lng=77.0,
            speed_kmh=-10.0,
            heading_deg=90.0,
            emergency=True,
            ts=time.time(),
        )
    # Heading >= 360
    with pytest.raises(ValidationError):
        AmbulanceTelemetry(
            lat=12.0,
            lng=77.0,
            speed_kmh=45.0,
            heading_deg=360.0,
            emergency=True,
            ts=time.time(),
        )


def test_vehicle_telemetry_validation():
    # Valid
    v = VehicleTelemetry(
        vehicle_id="veh_1",
        lat=12.9716,
        lng=77.5946,
        ts=time.time(),
    )
    assert v.vehicle_id == "veh_1"
    assert v.speed_kmh is None

    # Invalid lat
    with pytest.raises(ValidationError):
        VehicleTelemetry(
            vehicle_id="veh_1",
            lat=100.0,
            lng=77.5946,
            ts=time.time(),
        )

    # Empty vehicle_id
    with pytest.raises(ValidationError):
        VehicleTelemetry(
            vehicle_id="",
            lat=12.0,
            lng=77.0,
            ts=time.time(),
        )


def test_staleness_and_manager():
    mgr = WebSocketManager()
    now = time.time()

    # Ambulance state received 50 seconds ago
    amb_state = AmbulanceState(
        lat=12.9716,
        lng=77.5946,
        speed_kmh=40.0,
        heading_deg=90.0,
        emergency=True,
        ts=now - 50.0,
        received_at=now - 50.0,
    )
    mgr.set_ambulance_state(amb_state)
    assert amb_state.is_stale(max_age_seconds=30.0, current_time=now) is True
    assert mgr.get_fresh_ambulance_state(max_age_seconds=30.0) is None

    # Fresh state
    fresh_amb = AmbulanceState(
        lat=12.9716,
        lng=77.5946,
        speed_kmh=40.0,
        heading_deg=90.0,
        emergency=True,
        ts=now,
        received_at=now,
    )
    mgr.set_ambulance_state(fresh_amb)
    assert fresh_amb.is_stale(max_age_seconds=30.0, current_time=now) is False
    assert mgr.get_fresh_ambulance_state(max_age_seconds=30.0) is not None

    # Vehicle state
    fake_ws = object()
    mgr.add_vehicle("veh_1", fake_ws)
    v_state = VehicleState(
        vehicle_id="veh_1",
        lat=12.9720,
        lng=77.5950,
        ts=now,
        received_at=now,
    )
    mgr.set_vehicle_state("veh_1", v_state)
    fresh_vehs = mgr.get_fresh_vehicle_states(max_age_seconds=30.0)
    assert "veh_1" in fresh_vehs

    # Remove vehicle
    mgr.remove_vehicle("veh_1", fake_ws)
    assert not mgr.has_vehicle("veh_1")
    assert "veh_1" not in mgr.connected_vehicles()
    assert "veh_1" not in mgr.all_vehicle_states()
    assert mgr.get_fresh_vehicle_states() == {}


if __name__ == "__main__":
    test_ambulance_telemetry_valid()
    test_ambulance_telemetry_coordinate_out_of_range()
    test_ambulance_telemetry_invalid_speed_and_heading()
    test_vehicle_telemetry_validation()
    test_staleness_and_manager()
    print("STEP 4 validation tests PASSED successfully!")
