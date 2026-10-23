"""Comprehensive Test Suite for Camera, Neural Lane Detection, and Junction Priority Hardware.
"""

import time
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from ai.lane_model import load_model
from ai.lane_tracker import TemporalLaneTracker
from camera_manager import VehicleCameraManager
from junction_service import get_junction_service, JUNCTION_AUTH_KEY
from main import app
from models import AmbulanceState, LightAspects, SignalPriorityRequest
from websocket_manager import get_ws_manager, reset_ws_manager


@pytest.fixture(autouse=True)
def clean_singletons():
    reset_ws_manager()
    yield
    reset_ws_manager()


def _create_sample_road_frame(w=320, h=180) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[int(h * 0.45):, :] = (65, 65, 65)
    img[:int(h * 0.45), :] = (180, 150, 100)
    vp_x, vp_y = w // 2, int(h * 0.48)
    cv2.line(img, (int(w * 0.18), h), (vp_x - 15, vp_y), (255, 255, 255), 4)
    cv2.line(img, (int(w * 0.82), h), (vp_x + 15, vp_y), (255, 255, 255), 4)
    return img


def test_neural_lane_inference():
    """Verify PyTorch neural model loading, forward pass, and latency measurement."""
    model = load_model()
    assert model is not None
    assert model.is_loaded is True

    frame = _create_sample_road_frame()
    result = model.detect(frame)

    assert result["status"] == "inference_ok"
    assert result["lane"] in ("LEFT", "CENTER", "RIGHT")
    assert result["lane_confidence"] >= 0.50
    assert result["latency_ms"] > 0.0
    print(f"PASS: Neural inference verified (Lane={result['lane']}, Conf={result['lane_confidence']}, Latency={result['latency_ms']}ms)")


def test_temporal_lane_tracker():
    """Verify anti-flicker voting, smoothing, and illumination classification."""
    tracker = TemporalLaneTracker()

    # 1. Normal lighting with minor offset jitter
    t1 = tracker.update(raw_lane="CENTER", raw_offset_m=0.15, raw_conf=0.90, scene_brightness=110.0)
    assert t1["lane"] == "CENTER"
    assert t1["lighting_condition"] == "NORMAL"
    assert t1["lateral_offset_m"] == 0.15

    # 2. Smooth slight jitter
    t2 = tracker.update(raw_lane="CENTER", raw_offset_m=0.25, raw_conf=0.90, scene_brightness=110.0)
    assert t2["lane"] == "CENTER"
    # Smoothed value between 0.15 and 0.25
    assert 0.16 <= t2["lateral_offset_m"] <= 0.24

    # 3. Night / low light condition
    t_night = tracker.update(raw_lane="CENTER", raw_offset_m=0.20, raw_conf=0.85, scene_brightness=20.0)
    assert t_night["lighting_condition"] == "LOW_LIGHT_OR_NIGHT"

    # 4. Single-frame anomalous classification rejected by hysteresis
    t_anomaly = tracker.update(raw_lane="LEFT", raw_offset_m=-0.80, raw_conf=0.60, scene_brightness=110.0)
    # Window of [CENTER, CENTER, CENTER, LEFT] still retains CENTER!
    assert t_anomaly["lane"] == "CENTER"
    print("PASS: Temporal lane tracker smoothing and anti-flicker hysteresis verified")


def test_camera_manager_lifecycle():
    """Verify VehicleCameraManager startup, capture, and safe release."""
    mgr = VehicleCameraManager(vehicle_id="V_TEST", camera_source="prerecorded", target_fps=10.0)
    assert mgr.camera_enabled is False
    try:
        mgr.start()
        assert mgr.camera_enabled is True
        time.sleep(0.8)

        status = mgr.get_status()
        assert status["vehicle_id"] == "V_TEST"
        assert status["camera_enabled"] is True
        assert status["is_connected"] is True
        assert "prerecorded" in status["source_type"]
        assert status["frames_captured"] > 0
        assert mgr.latest_frame_jpeg is not None
        print(f"PASS: Camera manager captured {status['frames_captured']} frames (FPS={status['fps']})")
    finally:
        mgr.stop()
        assert mgr.camera_enabled is False
        assert mgr.is_connected is False


@pytest.mark.asyncio
async def test_eta_triggered_priority_logic():
    """Verify ETA calculation, distance thresholding, and priority triggering."""
    junc_svc = get_junction_service()
    cfg = junc_svc._configs["JUNC_01"]

    # 1. Distant ambulance (800m) -> No trigger
    far_amb = AmbulanceState(
        lat=cfg.lat - 0.0075,  # ~830m away
        lng=cfg.lng,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=time.time(),
        ambulance_id="AMB_TEST",
    )
    await junc_svc.evaluate_eta_and_trigger(far_amb)
    assert "JUNC_01" not in junc_svc._active_requests

    # 2. Non-emergency ambulance inside range -> No trigger
    non_emerg_amb = AmbulanceState(
        lat=cfg.lat - 0.002,  # ~220m away
        lng=cfg.lng,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=False,
        ts=time.time(),
        ambulance_id="AMB_TEST",
    )
    await junc_svc.evaluate_eta_and_trigger(non_emerg_amb)
    assert "JUNC_01" not in junc_svc._active_requests

    # 3. Approaching emergency ambulance (220m, 50 km/h, ETA ~16s) -> TRIGGERS PRIORITY!
    close_amb = AmbulanceState(
        lat=cfg.lat - 0.002,
        lng=cfg.lng,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=time.time(),
        ambulance_id="AMB_TEST",
    )
    await junc_svc.evaluate_eta_and_trigger(close_amb)
    assert "JUNC_01" in junc_svc._active_requests
    req = junc_svc._active_requests["JUNC_01"]
    assert req.junction_id == "JUNC_01"
    assert req.approach_id == "NORTH_SOUTH"
    assert req.eta_s <= 30.0
    assert req.auth_token == JUNCTION_AUTH_KEY
    print(f"PASS: Priority triggered successfully (ReqID={req.request_id}, ETA={req.eta_s}s)")


def test_junction_websocket_and_telemetry_flow():
    """Verify Junction ESP32 WebSocket connection, telemetry ingest, and status API."""
    client = TestClient(app)

    with client.websocket_connect("/ws/junction/JUNC_01") as ws:
        # 1. Receive welcome
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        assert welcome["junction_id"] == "JUNC_01"

        # 2. ESP32 emits telemetry packet
        telemetry = {
            "type": "junction_telemetry",
            "junction_id": "JUNC_01",
            "current_state": "PRIORITY_HOLD",
            "priority_active": True,
            "active_approach": "NORTH_SOUTH",
            "lights": {
                "approach_a": {"red": False, "yellow": False, "green": True},
                "approach_b": {"red": True, "yellow": False, "green": False},
            },
            "uptime_s": 45,
        }
        ws.send_json(telemetry)
        time.sleep(0.1)

        # 3. Query REST status API
        resp = client.get("/api/junction/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "JUNC_01" in data
        j_data = data["JUNC_01"]
        assert j_data["connected"] is True
        assert j_data["hardware_mode"] == "PHYSICAL_ESP32"
        assert j_data["current_state"] == "PRIORITY_HOLD"
        assert j_data["lights"]["approach_a"]["green"] is True
        assert j_data["lights"]["approach_b"]["red"] is True
        print("PASS: Junction ESP32 WebSocket and telemetry ingestion verified")


if __name__ == "__main__":
    test_neural_lane_inference()
    test_temporal_lane_tracker()
    test_camera_manager_lifecycle()
    test_junction_websocket_and_telemetry_flow()
    print("ALL CAMERA, ML, AND JUNCTION TESTS COMPLETED SUCCESSFULLY!")
