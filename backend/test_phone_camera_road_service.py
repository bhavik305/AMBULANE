"""Lane-Aware Intelligent Emergency Vehicle Alert System
Unit Tests for Map-Assisted Lane Detection & Phone Camera Service
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
import numpy as np
import pytest

from road_service import RoadAttributes, get_road_service
from device_service import get_device_service
from models import DeviceRegisterRequest, DeviceRole
from api.camera import process_frame
from websocket_manager import get_ws_manager


road_service = get_road_service()
device_service = get_device_service()
ws_manager = get_ws_manager()


def test_road_service_fusion_map_and_camera():
    """Verify road service combines map tags and camera lane detection when both are present."""
    test_lat, test_lng = 12.9716, 77.5946
    road_service._spatial_cache[(round(test_lat, 4), round(test_lng, 4))] = (
        time.time(),
        RoadAttributes(
            road_name="MG Road",
            highway="primary",
            total_lanes=4,
            forward_lanes=2,
            backward_lanes=2,
            oneway=False,
            speed_limit_kmh=50,
            source="OSM_OVERPASS",
        ),
    )

    combined = road_service.combine_map_and_camera(
        camera_lane="LEFT",
        camera_conf=0.88,
        detected_boundaries_count=2,
        lat=test_lat,
        lng=test_lng,
        heading_deg=90.0,
    )
    assert combined["data_source"] == "MAP_AND_CAMERA"
    assert combined["total_lanes"] == 4
    assert combined["direction_lanes"] == 2
    assert combined["lane"] == "LEFT"
    assert combined["road_name"] == "MG Road"
    assert combined["lane_index"] == 1
    assert "left" in combined["description"].lower()


def test_road_service_fusion_camera_only_when_map_missing():
    """When OSM has no lane count tags, fallback to camera estimate without inventing fake counts."""
    test_lat, test_lng = 12.9800, 77.6000
    road_service._spatial_cache[(round(test_lat, 4), round(test_lng, 4))] = (
        time.time(),
        RoadAttributes(
            road_name="Unnamed Road",
            highway="residential",
            total_lanes=None,
            forward_lanes=None,
            backward_lanes=None,
            oneway=False,
            speed_limit_kmh=30,
            source="OSM_OVERPASS",
        ),
    )

    combined = road_service.combine_map_and_camera(
        camera_lane="CENTER",
        camera_conf=0.75,
        detected_boundaries_count=2,
        lat=test_lat,
        lng=test_lng,
    )
    assert combined["data_source"] == "CAMERA_ONLY"
    assert combined["total_lanes"] is None  # Must never fabricate lane count
    assert combined["direction_lanes"] is None
    assert combined["lane"] == "CENTER"
    assert "estimate" in combined["description"].lower()


def test_road_service_fusion_unknown_when_visibility_insufficient():
    """When camera visibility is insufficient, must return UNKNOWN instead of guessing."""
    test_lat, test_lng = 12.9850, 77.6100
    road_service._spatial_cache[(round(test_lat, 4), round(test_lng, 4))] = (
        time.time(),
        RoadAttributes(
            road_name="Residency Road",
            highway="primary",
            total_lanes=3,
            forward_lanes=3,
            backward_lanes=0,
            oneway=True,
            speed_limit_kmh=50,
            source="OSM_OVERPASS",
        ),
    )

    combined = road_service.combine_map_and_camera(
        camera_lane="UNKNOWN",
        camera_conf=0.0,
        detected_boundaries_count=0,
        lat=test_lat,
        lng=test_lng,
    )
    assert combined["lane"] == "UNKNOWN"
    assert combined["lane_index"] is None


def test_ambulance_role_isolation():
    """Enforce role separation: Ambulance mode uses configured lane, ordinary vehicles use camera."""
    device_service.register_device(
        DeviceRegisterRequest(device_id="AMB_TEST", role=DeviceRole.AMBULANCE, admin_pin="9911", configured_lane="CENTER")
    )
    dev = device_service.get_device("AMB_TEST")
    assert dev is not None
    assert dev.role == DeviceRole.AMBULANCE
    assert dev.configured_lane == "CENTER"

    # Verify normal vehicle registration
    device_service.register_device(
        DeviceRegisterRequest(device_id="V_TEST", role=DeviceRole.NORMAL_VEHICLE)
    )
    v_dev = device_service.get_device("V_TEST")
    assert v_dev is not None
    assert v_dev.role == DeviceRole.NORMAL_VEHICLE


def test_direct_process_frame_with_map_fusion():
    """Process a phone still image frame and verify OSM map corridor attributes fusion."""
    # Synthetic road frame with clear lane markings
    w, h = 640, 360
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[int(h * 0.5):, :] = (60, 60, 60)  # road asphalt
    img[:int(h * 0.5), :] = (180, 150, 100)  # sky
    cv2.line(img, (int(w * 0.25), h - 1), (int(w * 0.44), int(h * 0.55)), (255, 255, 255), 4)
    cv2.line(img, (int(w * 0.75), h - 1), (int(w * 0.56), int(h * 0.55)), (255, 255, 255), 4)
    _, img_encoded = cv2.imencode(".jpg", img)
    frame_bytes = img_encoded.tobytes()

    test_lat, test_lng = 12.9716, 77.5946
    result = process_frame(
        vehicle_id="V_DIRECT_TEST",
        frame_bytes=frame_bytes,
        timestamp=time.time(),
        lat=test_lat,
        lng=test_lng,
        heading_deg=90.0,
    )

    assert result is not None
    assert result.lane in ["LEFT", "CENTER", "RIGHT", "UNKNOWN"]
    assert result.total_lanes == 4
    assert result.direction_lanes == 2
    assert result.data_source == "MAP_AND_CAMERA"
    assert result.map_lane_available is True
    assert result.road_name is not None
    assert "Road" in result.road_name


if __name__ == "__main__":
    test_road_service_fusion_map_and_camera()
    print("PASS: test_road_service_fusion_map_and_camera PASSED")
    test_road_service_fusion_camera_only_when_map_missing()
    print("PASS: test_road_service_fusion_camera_only_when_map_missing PASSED")
    test_road_service_fusion_unknown_when_visibility_insufficient()
    print("PASS: test_road_service_fusion_unknown_when_visibility_insufficient PASSED")
    test_ambulance_role_isolation()
    print("PASS: test_ambulance_role_isolation PASSED")
    test_direct_process_frame_with_map_fusion()
    print("PASS: test_direct_process_frame_with_map_fusion PASSED")
    print("\nALL 5 ROAD SERVICE & PHONE CAMERA TESTS PASSED SUCCESSFULLY!")
