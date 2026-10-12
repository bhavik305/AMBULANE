"""Step 8 AI Lane and Path Detection Tests."""

import time
import cv2
import numpy as np
from fastapi.testclient import TestClient

from ai.lane_detection import detect_lane
from ai.lane_model import load_model
from ai.preprocessing import decode_frame, preprocess_frame
from main import app
from websocket_manager import get_ws_manager


def _create_synthetic_road_frame(shift_x: int = 0) -> bytes:
    """Generate a realistic synthetic forward camera road image with lanes."""
    w, h = 640, 360
    img = np.zeros((h, w, 3), dtype=np.uint8)

    # Road asphalt gray
    img[int(h * 0.5):, :] = (60, 60, 60)

    # Sky / background top
    img[:int(h * 0.5), :] = (180, 150, 100)

    # Left white lane line (angled towards vanishing point)
    vp_x, vp_y = w // 2 + shift_x, int(h * 0.52)
    left_bottom_x = int(w * 0.20) + shift_x
    right_bottom_x = int(w * 0.80) + shift_x

    cv2.line(img, (left_bottom_x, h), (vp_x - 30, vp_y), (255, 255, 255), 10)
    # Right white lane line
    cv2.line(img, (right_bottom_x, h), (vp_x + 30, vp_y), (255, 255, 255), 10)

    # Encode to JPEG
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def test_preprocessing():
    frame_bytes = _create_synthetic_road_frame()
    bgr = decode_frame(frame_bytes)
    assert bgr is not None
    assert bgr.shape == (360, 640, 3)

    _, roi = preprocess_frame(frame_bytes, target_size=(640, 360))
    assert roi is not None
    assert roi.shape == (360, 640, 3)
    print("PASS: Preprocessing and decoding verified")


def test_model_scaffold():
    model = load_model()
    assert model is not None
    # Model scaffold correctly reports is_loaded = False when weights not present
    assert model.backend_type in ("unloaded_scaffold", "pytorch_torchscript")
    print(f"PASS: Model loader verified (backend={model.backend_type})")


def test_centered_lane_detection():
    frame_bytes = _create_synthetic_road_frame(shift_x=0)
    result = detect_lane(frame_bytes, vehicle_id="veh_lane_1")

    assert result is not None
    assert result["vehicle_id"] == "veh_lane_1"
    assert result["lane"] == "CENTER", f"Expected CENTER, got {result['lane']}"
    assert result["lane_confidence"] >= 0.70
    assert result["detected_lanes_count"] == 2
    print("PASS: Centered lane detection verified ->", result)


def test_shifted_lane_detection():
    # Shift road lanes left by 80px (meaning vehicle is on the RIGHT relative to center)
    frame_bytes = _create_synthetic_road_frame(shift_x=-80)
    result = detect_lane(frame_bytes, vehicle_id="veh_lane_2")

    assert result is not None
    assert result["lane"] == "RIGHT", f"Expected RIGHT, got {result['lane']}"
    print("PASS: Right-shifted vehicle position verified ->", result)


def test_blank_image_safe_handling():
    # Pure blank image with no road marks
    blank = np.zeros((360, 640, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", blank)
    result = detect_lane(buf.tobytes(), vehicle_id="veh_blank")

    assert result is not None
    assert result["lane"] is None
    assert result["lane_confidence"] == 0.0
    print("PASS: Blank image safely handled without failure ->", result)


def test_full_camera_api_integration():
    client = TestClient(app)
    ws_mgr = get_ws_manager()

    fake_ws = object()
    ws_mgr.add_vehicle("veh_integration", fake_ws)

    # Set initial vehicle state
    from models import VehicleState
    ws_mgr.set_vehicle_state(
        "veh_integration",
        VehicleState(
            vehicle_id="veh_integration",
            lat=12.9716,
            lng=77.5946,
            ts=time.time(),
        ),
    )

    frame_bytes = _create_synthetic_road_frame(shift_x=0)
    resp = client.post(
        "/api/camera/frame/veh_integration",
        files={"file": ("road.jpg", frame_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accepted"] is True
    assert data["result"]["lane"] == "CENTER"

    # Verify vehicle state in WebSocketManager was updated with lane info!
    v_st = ws_mgr.get_vehicle_state("veh_integration")
    assert v_st is not None
    assert v_st.lane == "CENTER"
    assert v_st.lane_confidence >= 0.70
    print("PASS: Camera API merged lane prediction into VehicleState ->", v_st.lane, v_st.lane_confidence)

    ws_mgr.remove_vehicle("veh_integration", fake_ws)


if __name__ == "__main__":
    test_preprocessing()
    test_model_scaffold()
    test_centered_lane_detection()
    test_shifted_lane_detection()
    test_blank_image_safe_handling()
    test_full_camera_api_integration()
    print("ALL STEP 8 AI Lane Detection tests PASSED successfully!")
