"""Ambulance WebSocket test for STEP 2.

Reuses the existing backend from Step 1. Does NOT modify any Step 1 code.

Run from the backend/ directory:

    python test_ambulance_ws.py
"""

import asyncio
import json
import sys
import urllib.request

import websockets

BASE = "ws://localhost:8000"
REST = "http://localhost:8000"


def _print(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


async def _fetch_status():
    with urllib.request.urlopen(f"{REST}/status", timeout=5) as resp:
        return json.loads(resp.read().decode())


async def main():
    # TEST 1: Backend starts.
    _print("TEST 1: Backend starts")
    try:
        status = await _fetch_status()
    except Exception as exc:
        print("FAIL: backend not reachable:", exc)
        sys.exit(1)
    assert status["status"] == "online"
    print("PASS: backend online")

    # TEST 2: Ambulance WebSocket connects.
    _print("TEST 2: Ambulance WebSocket connects")
    ws = await websockets.connect(f"{BASE}/ws/ambulance")
    status = await _fetch_status()
    assert status["ambulance_connected"] is True
    print("PASS: ambulance connected")

    # TEST 3: Valid telemetry accepted.
    _print("TEST 3: Valid telemetry accepted")
    telemetry = {
        "lat": 10.000001,
        "lng": 76.000001,
        "speed_kmh": 40,
        "heading_deg": 90,
        "emergency": True,
        "ts": 1750000000,
    }
    await ws.send(json.dumps(telemetry))
    ack = json.loads(await ws.recv())
    assert ack["type"] == "ack", ack
    print("PASS: valid telemetry accepted ->", ack["message"])

    # TEST 4: Ambulance state updates.
    _print("TEST 4: Ambulance state updates")
    status = await _fetch_status()
    st = status["ambulance_state"]
    assert st["lat"] == 10.000001
    assert st["lng"] == 76.000001
    assert st["speed_kmh"] == 40
    assert st["heading_deg"] == 90
    assert st["emergency"] is True
    assert st["ts"] == 1750000000
    print("PASS: ambulance state updated ->", json.dumps(st))

    # TEST 5: Invalid JSON does not crash.
    _print("TEST 5: Invalid JSON does not crash")
    await ws.send("not valid json")
    err = json.loads(await ws.recv())
    assert err["type"] == "error"
    status = await _fetch_status()
    assert status["status"] == "online"
    print("PASS: invalid JSON handled ->", err["message"])

    # TEST 6: Invalid telemetry does not crash.
    _print("TEST 6: Invalid telemetry does not crash")
    await ws.send(json.dumps({"lat": "bad", "lng": 76.0}))
    err2 = json.loads(await ws.recv())
    assert err2["type"] == "error"
    status = await _fetch_status()
    assert status["status"] == "online"
    print("PASS: invalid telemetry handled ->", err2["message"])

    # TEST 9: Multiple telemetry messages update the latest state.
    _print("TEST 9: Multiple telemetry messages update latest state")
    for i in range(3):
        await ws.send(json.dumps({
            "lat": 10.0 + i * 0.001,
            "lng": 76.0 + i * 0.001,
            "speed_kmh": 40 + i,
            "heading_deg": 90,
            "emergency": True,
            "ts": 1750000000 + i,
        }))
        await ws.recv()
    status = await _fetch_status()
    st = status["ambulance_state"]
    # Loop sends i=0,1,2 -> lat = 10.0, 10.001, 10.002
    assert st["lat"] == 10.002, st
    assert st["speed_kmh"] == 42, st
    print("PASS: latest state is the most recent message ->", st["lat"], st["speed_kmh"])

    # TEST 7: Ambulance disconnect handled.
    _print("TEST 7: Ambulance disconnect handled")
    await ws.close()
    await asyncio.sleep(0.2)
    status = await _fetch_status()
    assert status["ambulance_connected"] is False
    assert status["ambulance_state"] is not None  # last known state preserved
    print("PASS: disconnect handled, ambulance_connected=False")

    # TEST 8: /status still works.
    _print("TEST 8: /status still works")
    status = await _fetch_status()
    assert status["status"] == "online"
    assert "ambulance_connected" in status
    assert "ambulance_state" in status
    print("PASS: /status works ->", json.dumps(status))

    _print("ALL AMBULANCE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())