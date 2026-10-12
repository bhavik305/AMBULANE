"""Simulation + test script for STEP 1 backend.

Run from the backend/ directory:

    python simulate.py
"""

import asyncio
import json
import sys
import time
import urllib.request

import websockets

BASE = "ws://localhost:8000"
REST = "http://localhost:8000"


def _print(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


async def _fetch_status():
    """Helper to GET /status using urllib (no extra deps)."""
    with urllib.request.urlopen(f"{REST}/status", timeout=5) as resp:
        return json.loads(resp.read().decode())


async def test_ambulance():
    _print("TEST 2-3: Ambulance WebSocket connect + telemetry")
    async with websockets.connect(f"{BASE}/ws/ambulance") as ws:
        telemetry = {
            "lat": 12.9716,
            "lng": 77.5946,
            "speed_kmh": 45.0,
            "heading_deg": 90.0,
            "emergency": True,
            "ts": time.time(),
        }
        await ws.send(json.dumps(telemetry))
        ack = json.loads(await ws.recv())
        print("ACK:", json.dumps(ack, indent=2))

        # Send malformed data -> server must NOT crash.
        await ws.send("not json")
        err = json.loads(await ws.recv())
        print("ERROR (expected):", json.dumps(err, indent=2))

        await ws.send(json.dumps({"lat": "bad", "lng": 77.0}))
        err2 = json.loads(await ws.recv())
        print("ERROR2 (expected):", json.dumps(err2, indent=2))

    # After disconnect, /status should show ambulance disconnected.
    # NOTE: we intentionally KEEP the last known ambulance state so /status
    # can still report where the ambulance last was. Only the connection
    # flag is cleared.
    status = await _fetch_status()
    print("Status after disconnect:", json.dumps(status, indent=2))
    assert status["ambulance_connected"] is False, "ambulance should be disconnected"
    assert status["ambulance_state"] is not None, "last known state should persist"
    assert status["ambulance_state"]["emergency"] is True
    print("PASS: ambulance disconnected but last state preserved")


async def test_vehicles():
    _print("TEST 4-7: Participant vehicles connect + telemetry + disconnect")
    async with websockets.connect(f"{BASE}/ws/vehicle/car_a") as wa, \
               websockets.connect(f"{BASE}/ws/vehicle/car_b") as wb:

        # Minimal client (lat/lng only) - backward compatibility.
        await wa.send(json.dumps({"vehicle_id": "car_a", "lat": 12.9716, "lng": 77.5946, "ts": time.time()}))
        print("car_a ACK:", json.loads(await wa.recv()))

        # Richer client with speed/heading.
        await wb.send(json.dumps({
            "vehicle_id": "car_b",
            "lat": 12.9720,
            "lng": 77.5950,
            "speed_kmh": 30.0,
            "heading_deg": 180.0,
            "ts": time.time(),
        }))
        print("car_b ACK:", json.loads(await wb.recv()))

        status = await _fetch_status()
        print("Status with 2 vehicles:", json.dumps(status, indent=2))
        assert status["vehicle_count"] == 2, f"expected 2 vehicles, got {status['vehicle_count']}"
        assert "car_a" in status["connected_vehicles"]
        assert "car_b" in status["connected_vehicles"]

        # Malformed -> no crash.
        await wa.send("garbage")
        print("car_a error (expected):", json.loads(await wa.recv()))

    # After both disconnect, count should be 0.
    status = await _fetch_status()
    print("Status after both disconnect:", json.dumps(status, indent=2))
    assert status["vehicle_count"] == 0, "vehicles should be cleared"
    print("PASS: vehicles cleaned up on disconnect")


async def test_malformed_global():
    _print("TEST 9: Malformed telemetry does not crash the server")
    async with websockets.connect(f"{BASE}/ws/vehicle/car_x") as wx:
        for bad in ["", "not-json", "123", "[]", json.dumps({"lat": "x"}), json.dumps({"vehicle_id": "car_x"})]:
            try:
                await wx.send(bad if isinstance(bad, str) else json.dumps(bad))
                resp = json.loads(await wx.recv())
                print(f"  bad={bad!r} -> {resp}")
            except Exception as exc:  # noqa: BLE001
                print(f"  bad={bad!r} -> exception {exc}")
    status = await _fetch_status()
    assert status["status"] == "online", "server should still be online"
    print("PASS: server survived malformed data")


async def main():
    _print("TEST 1: Backend starts successfully")
    try:
        status = await _fetch_status()
    except Exception as exc:  # noqa: BLE001
        print("FAIL: backend not reachable:", exc)
        sys.exit(1)
    print("Initial /status:", json.dumps(status, indent=2))
    assert status["status"] == "online"
    print("PASS: backend is online")

    await test_ambulance()
    await test_vehicles()
    await test_malformed_global()

    _print("TEST 8: GET /status reports the current state")
    status = await _fetch_status()
    print("Final /status:", json.dumps(status, indent=2))
    assert status["status"] == "online"
    assert status["ambulance_connected"] is False
    assert status["vehicle_count"] == 0
    print("PASS: /status correct")

    _print("ALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())