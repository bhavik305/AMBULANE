"""Frontend & WebSocket Integration Test Suite."""

import time
import pytest
from fastapi.testclient import TestClient

from main import app
from websocket_manager import get_ws_manager, reset_ws_manager


@pytest.fixture(autouse=True)
def clean_manager():
    reset_ws_manager()
    yield
    reset_ws_manager()


def test_rest_endpoints():
    client = TestClient(app)

    # 1. /health probe
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

    # 2. /status snapshot
    r = client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "online"
    assert "ambulance_connected" in data
    assert "connected_vehicles" in data

    # 3. Static frontend index mount
    r = client.get("/frontend/index.html")
    assert r.status_code == 200
    assert "Lane-Aware EVAS" in r.text
    assert "EVAS" in r.text

    # 4. /app redirect
    r = client.get("/app", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/frontend/index.html" in r.headers["location"]

    # 5. /ambulance redirect
    r = client.get("/ambulance", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/frontend/ambulance/index.html" in r.headers["location"]


def test_vehicle_ws_and_alert_dispatch():
    client = TestClient(app)

    with client.websocket_connect("/ws/vehicle/V002") as v_ws:
        # 1. Vehicle sends initial telemetry with Flutter-style alias fields
        v_payload = {
            "latitude": 12.9748,
            "longitude": 77.5946,
            "speed": 40.0,
            "heading": 0.0,
            "lane": 2,
            "timestamp": "2026-10-22T14:00:00Z",
        }
        v_ws.send_json(v_payload)

        # Vehicle should receive ack
        v_ack = v_ws.receive_json()
        assert v_ack["type"] == "ack"
        assert v_ack["vehicle_id"] == "V002"

        # 2. Ambulance connects and sends emergency telemetry
        with client.websocket_connect("/ws/ambulance") as amb_ws:
            amb_payload = {
                "lat": 12.9716,
                "lng": 77.5946,
                "speed_kmh": 70.0,
                "heading_deg": 0.0,
                "emergency": True,
                "ts": time.time(),
            }
            amb_ws.send_json(amb_payload)

            amb_ack = amb_ws.receive_json()
            assert amb_ack["type"] == "ack"

            # 3. Vehicle should receive a fleet_update or emergency_alert
            # Read messages until we get emergency_alert
            got_alert = False
            for _ in range(5):
                msg = v_ws.receive_json()
                if msg.get("type") == "emergency_alert":
                    assert msg["to_id"] == "V002"
                    assert msg["emergency_state"] is True
                    assert msg["distance"] > 0
                    assert msg["ambulance_lane"] == 2
                    got_alert = True
                    break
                elif msg.get("type") == "fleet_update":
                    assert "ambulance" in msg
            assert got_alert, "Vehicle should have received targeted emergency_alert"

            # 4. Vehicle clears lane by shifting to Lane 1 (Left)
            clear_lane_payload = {
                "lat": 12.9748,
                "lng": 77.5946,
                "speed_kmh": 40.0,
                "heading_deg": 0.0,
                "lane": "1",
                "ts": time.time(),
            }
            v_ws.send_json(clear_lane_payload)
            v_ack2 = v_ws.receive_json()
            assert v_ack2["type"] == "ack"

            # Vehicle should receive emergency_clear or safe clearance
            got_clear = False
            for _ in range(5):
                msg = v_ws.receive_json()
                if msg.get("type") == "emergency_clear":
                    assert msg["to_id"] == "V002"
                    assert msg["emergency_state"] is False
                    got_clear = True
                    break
                elif msg.get("type") == "fleet_update":
                    pass
            assert got_clear, "Vehicle should receive clearance after switching to lane 1"


def test_vehicle_ws_malformed_resilience():
    client = TestClient(app)

    with client.websocket_connect("/ws/vehicle/V999") as ws:
        # Non-JSON text frame
        ws.send_text("not a json payload")
        err = ws.receive_json()
        assert err["type"] == "error"

        # Invalid coordinate
        ws.send_json({"lat": 999.0, "lng": 77.0, "ts": time.time()})
        err2 = ws.receive_json()
        assert err2["type"] == "error"

    # Verify server stayed healthy
    r = client.get("/health")
    assert r.status_code == 200
