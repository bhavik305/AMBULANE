"""Step 3 phone client contract test.

Simulates the phone-based ambulance GPS client against the EXISTING
backend. Verifies the phone telemetry format is accepted by the
Step 2 ambulance WebSocket and updates backend state.

Run from the backend/ directory:

    python test_phone_ambulance.py
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
    # TEST 1: Open phone page / backend reachable.
    _print("TEST 1: Backend reachable (phone page would load)")
    try:
        status = await _fetch_status()
    except Exception as exc:
        print("FAIL: backend not reachable:", exc)
        sys.exit(1)
    assert status["status"] == "online"
    print("PASS: backend online")

    # TEST 4: Phone connects to /ws/ambulance.
    _print("TEST 4: Phone connects to /ws/ambulance")
    ws = await websockets.connect(f"{BASE}/ws/ambulance")
    status = await _fetch_status()
    assert status["ambulance_connected"] is True
    print("PASS: phone connected to /ws/ambulance")

    # TEST 3/5/6: Phone obtains lat/lng and backend receives telemetry.
    _print("TEST 3/5/6: Phone sends telemetry; backend receives + updates state")
    phone_telemetry = {
        "lat": 10.123456,
        "lng": 76.123456,
        "speed_kmh": 40.5,
        "heading_deg": 90.0,
        "emergency": True,
        "ts": 1750000000,
        "source": "phone",
    }
    await ws.send(json.dumps(phone_telemetry))
    ack = json.loads(await ws.recv())
    assert ack["type"] == "ack", ack
    status = await _fetch_status()
    st = status["ambulance_state"]
    assert st["lat"] == 10.123456, st
    assert st["lng"] == 76.123456, st
    assert st["speed_kmh"] == 40.5, st
    assert st["heading_deg"] == 90.0, st
    assert st["emergency"] is True, st
    assert st["ts"] == 1750000000, st
    print("PASS: backend state updated from phone telemetry")

    # TEST 7: Moving the phone changes coordinates.
    _print("TEST 7: Moving the phone changes coordinates")
    await ws.send(json.dumps({
        "lat": 10.124000, "lng": 76.125000, "speed_kmh": 41.0,
        "heading_deg": 95.0, "emergency": True, "ts": 1750000001, "source": "phone"
    }))
    await ws.recv()
    status = await _fetch_status()
    st = status["ambulance_state"]
    assert st["lat"] == 10.124000, st
    assert st["lng"] == 76.125000, st
    print("PASS: coordinates updated after phone moved")

    # TEST 8: Emergency ON transmitted.
    _print("TEST 8: Emergency ON transmitted")
    await ws.send(json.dumps({
        "lat": 10.124000, "lng": 76.125000, "speed_kmh": 41.0,
        "heading_deg": 95.0, "emergency": True, "ts": 1750000002, "source": "phone"
    }))
    await ws.recv()
    status = await _fetch_status()
    assert status["ambulance_state"]["emergency"] is True
    print("PASS: emergency ON reflected in backend state")

    # TEST 9: Emergency OFF transmitted.
    _print("TEST 9: Emergency OFF transmitted")
    await ws.send(json.dumps({
        "lat": 10.124000, "lng": 76.125000, "speed_kmh": 41.0,
        "heading_deg": 95.0, "emergency": False, "ts": 1750000003, "source": "phone"
    }))
    await ws.recv()
    status = await _fetch_status()
    assert status["ambulance_state"]["emergency"] is False
    print("PASS: emergency OFF reflected in backend state")

    # GPS fallback: speed/heading unavailable -> 0.
    _print("GPS FALLBACK: speed/heading unavailable -> 0")
    await ws.send(json.dumps({
        "lat": 10.124000, "lng": 76.125000,
        "speed_kmh": 0, "heading_deg": 0,
        "emergency": False, "ts": 1750000004, "source": "phone"
    }))
    await ws.recv()
    status = await _fetch_status()
    assert status["ambulance_state"]["speed_kmh"] == 0
    assert status["ambulance_state"]["heading_deg"] == 0
    print("PASS: unavailable speed/heading safely fall back to 0")

    # TEST 10: Phone disconnects cleanly.
    _print("TEST 10: Phone disconnects cleanly")
    await ws.close()
    await asyncio.sleep(0.3)
    status = await _fetch_status()
    assert status["ambulance_connected"] is False
    assert status["ambulance_state"] is not None  # last known preserved
    print("PASS: phone disconnected cleanly")

    # TEST 11: Existing /status still works.
    _print("TEST 11: Existing /status still works")
    status = await _fetch_status()
    assert status["status"] == "online"
    assert "ambulance_connected" in status
    assert "ambulance_state" in status
    assert "connected_vehicles" in status
    assert "vehicle_count" in status
    print("PASS: /status unchanged")

    # TEST 12: Step 1/2 behavior unchanged (re-run Step 2 ambulance test).
    _print("TEST 12: Step 2 ambulance test still passes")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "test_ambulance_ws.py",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = (stdout or b"").decode()
    assert "ALL AMBULANCE TESTS PASSED" in out, out + (stderr or b"").decode()
    print("PASS: Step 2 test still passes")

    _print("ALL STEP 3 PHONE TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())