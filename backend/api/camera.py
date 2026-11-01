"""
Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 1 — Backend Foundation + Real-Time Communication

api/camera.py
=============
FUTURE CAMERA / AI PIPELINE (STEP 3).

This module is intentionally a STUB in Step 1.

The eventual flow for STEP 3 is:

    Phone camera
        ↓ (POST /api/camera/frame)
    camera API  ->  ai/preprocessing.py  ->  ai/lane_detection.py
        ↓
    lane result
        ↓
    matching_engine  ->  targeted alert delivery

In Step 1 we define:

- A clean REST interface for receiving camera frames.
- A placeholder `process_frame()` that documents the contract.

We DO NOT implement the ML model, and we DO NOT return fake lane
results such as "CENTER" to make the system look complete.

Public contract (STEP 3 will implement the bodies):
    process_frame(frame_payload) -> LaneDetectionResult
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from typing import Optional, Any, Union

from fastapi import APIRouter, File, UploadFile, HTTPException, Query, status
from pydantic import BaseModel, Field
from PIL import Image

from device_service import get_device_service, DeviceRole
from road_service import get_road_service
from websocket_manager import get_ws_manager

logger = logging.getLogger("backend.api.camera")

router = APIRouter(tags=["camera"])

MAX_FRAME_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB maximum
MIN_FRAME_SIZE_BYTES = 100               # 100 bytes minimum
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


def detect_image_format(data: bytes) -> Optional[str]:
    """Inspect magic header bytes to verify valid image formats."""
    if len(data) < 12:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class LaneDetectionResult(BaseModel):
    """Result of running lane detection on a camera frame, combined with OSM road data."""

    vehicle_id: str = Field(..., description="Vehicle the frame belongs to")
    lane: Optional[str] = Field(
        default=None,
        description="Lane label: 'LEFT', 'CENTER', 'RIGHT' or 'UNKNOWN'",
    )
    lane_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence 0..1 for the lane label",
    )
    timestamp: float = Field(..., description="Unix timestamp when frame was processed")
    processing_time_ms: Optional[float] = Field(
        default=None, description="Inference and processing latency in ms"
    )
    detected_lanes_count: Optional[int] = Field(
        default=None, description="Number of detected lane boundaries from camera"
    )
    total_lanes: Optional[int] = Field(
        default=None, description="Total road lanes from OpenStreetMap evidence"
    )
    direction_lanes: Optional[int] = Field(
        default=None, description="Direction-specific lane count from OpenStreetMap"
    )
    road_name: Optional[str] = Field(
        default=None, description="Matched road name from OpenStreetMap"
    )
    data_source: str = Field(
        default="CAMERA_ONLY",
        description="Data source: 'MAP_AND_CAMERA', 'CAMERA_ONLY', 'MAP_ONLY', or 'UNKNOWN'",
    )
    map_lane_available: bool = Field(
        default=False, description="Whether OpenStreetMap provided explicit lane count"
    )
    lane_index: Optional[int] = Field(
        default=None, description="Specific lane index e.g. Lane 2 of 3"
    )
    description: Optional[str] = Field(
        default=None, description="Human readable explanation of the lane result"
    )
    overlay_frame_b64: Optional[str] = Field(
        default=None, description="Annotated snapshot frame JPEG base64 encoded"
    )


class FrameResponse(BaseModel):
    """Response returned by POST /api/camera/frame."""

    accepted: bool
    vehicle_id: str
    message: str
    result: Optional[LaneDetectionResult] = None


def process_frame(
    vehicle_id: str,
    frame_bytes: bytes,
    timestamp: Optional[float] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    heading_deg: Optional[float] = None,
) -> Optional[LaneDetectionResult]:
    """Run the dual-engine lane detection pipeline on a single validated frame and fuse with OSM."""
    t0 = time.time()
    ts = timestamp or t0

    try:
        from ai.lane_detection import detect_lane
        lane_info = detect_lane(frame_bytes, vehicle_id=vehicle_id, timestamp=ts)
    except Exception as exc:  # noqa: BLE001
        logger.error("Lane detection error for vehicle %s: %s", vehicle_id, exc)
        return None

    if lane_info is None:
        return None

    # Retrieve vehicle coordinates for OSM road segment matching
    ws_mgr = get_ws_manager()
    v_state = ws_mgr.get_vehicle_state(vehicle_id)

    curr_lat = lat
    curr_lng = lng
    curr_heading = heading_deg

    if curr_lat is None or curr_lng is None:
        if v_state is not None and not v_state.is_stale(30.0):
            curr_lat = v_state.lat
            curr_lng = v_state.lng
            if curr_heading is None:
                curr_heading = v_state.heading_deg

    # Combine camera AI detection with OpenStreetMap road data
    road_svc = get_road_service()
    fused = road_svc.combine_map_and_camera(
        camera_lane=lane_info.get("lane"),
        camera_conf=lane_info.get("lane_confidence"),
        detected_boundaries_count=lane_info.get("detected_lanes_count", 0),
        lat=curr_lat,
        lng=curr_lng,
        heading_deg=curr_heading,
    )

    proc_ms = round((time.time() - t0) * 1000.0, 1)
    res = LaneDetectionResult(
        vehicle_id=vehicle_id,
        lane=fused.get("lane"),
        lane_confidence=fused.get("confidence"),
        timestamp=ts,
        processing_time_ms=proc_ms,
        detected_lanes_count=lane_info.get("detected_lanes_count", 0),
        total_lanes=fused.get("total_lanes"),
        direction_lanes=fused.get("direction_lanes"),
        road_name=fused.get("road_name"),
        data_source=fused.get("data_source", "CAMERA_ONLY"),
        map_lane_available=fused.get("map_lane_available", False),
        lane_index=fused.get("lane_index"),
        description=fused.get("description"),
        overlay_frame_b64=lane_info.get("overlay_frame_b64"),
    )

    # Merge lane prediction into active vehicle state
    if v_state is not None and res.lane is not None:
        v_state.lane = res.lane
        v_state.lane_confidence = res.lane_confidence
        ws_mgr.set_vehicle_state(vehicle_id, v_state)
        logger.info(
            "Updated vehicle %s lane state to %s (conf=%.2f, source=%s, OSM lanes=%s)",
            vehicle_id,
            res.lane,
            res.lane_confidence or 0.0,
            res.data_source,
            res.total_lanes,
        )

    # Ingest into VehicleCameraManager for preview and telemetry status
    from camera_manager import get_camera_manager
    cam_mgr = get_camera_manager(vehicle_id=vehicle_id)
    preview_bytes = None
    if lane_info.get("overlay_frame_b64"):
        try:
            preview_bytes = base64.b64decode(lane_info["overlay_frame_b64"])
        except Exception:
            pass
    cam_mgr.ingest_uploaded_frame(
        frame_bytes=frame_bytes,
        vehicle_id=vehicle_id,
        timestamp=ts,
        result_dict=res.model_dump(),
        annotated_jpeg_bytes=preview_bytes,
    )

    return res


@router.post("/api/camera/frame/{vehicle_id}", response_model=FrameResponse)
async def upload_frame(
    vehicle_id: str,
    file: UploadFile = File(..., description="Camera frame image bytes"),
    lat: Optional[float] = Query(default=None, ge=-90.0, le=90.0, description="Phone GPS latitude"),
    lng: Optional[float] = Query(default=None, ge=-180.0, le=180.0, description="Phone GPS longitude"),
    heading_deg: Optional[float] = Query(default=None, ge=0.0, lt=360.0, description="Vehicle heading in degrees"),
    speed_kmh: Optional[float] = Query(default=None, ge=0.0, description="Vehicle speed in km/h"),
) -> FrameResponse:
    """Receive and validate camera frame from a participant smartphone vehicle."""
    # 0. Read bytes in memory immediately to consume upload stream
    frame_bytes = await file.read()
    file_size = len(frame_bytes)

    # 1. Validate vehicle ID format
    if not re.match(r"^[A-Za-z0-9_-]{1,32}$", vehicle_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid vehicle_id format: '{vehicle_id}'. Must be alphanumeric 1-32 chars.",
        )

    # 2. Device role validation: Ambulance uses configured designated lane; camera is for normal vehicles
    dev_svc = get_device_service()
    dev = dev_svc.get_device(vehicle_id)
    if dev is not None and dev.role == DeviceRole.AMBULANCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ambulance uses configured designated lane; camera lane detection is for normal vehicles.",
        )

    ws_manager = get_ws_manager()

    # If coordinates are supplied with frame, synchronize immediately into vehicle state
    now_ts = time.time()
    if lat is not None and lng is not None:
        from models import VehicleState
        existing = ws_manager.get_vehicle_state(vehicle_id)
        if existing is not None:
            existing.lat = lat
            existing.lng = lng
            if heading_deg is not None:
                existing.heading_deg = heading_deg
            if speed_kmh is not None:
                existing.speed_kmh = speed_kmh
            existing.ts = now_ts
            existing.received_at = now_ts
            ws_manager.set_vehicle_state(vehicle_id, existing)
        else:
            new_state = VehicleState(
                vehicle_id=vehicle_id,
                lat=lat,
                lng=lng,
                heading_deg=heading_deg,
                speed_kmh=speed_kmh,
                ts=now_ts,
                received_at=now_ts,
            )
            ws_manager.set_vehicle_state(vehicle_id, new_state)

    # Check vehicle registration in ws_manager or device_service
    if not ws_manager.has_vehicle(vehicle_id) and not ws_manager.get_vehicle_state(vehicle_id):
        # Auto-register normal vehicle if valid
        from models import DeviceRegisterRequest
        dev_svc.register_device(DeviceRegisterRequest(device_id=vehicle_id, role=DeviceRole.NORMAL_VEHICLE))

    # 3. File size validation
    if file_size < MIN_FRAME_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Frame payload too small ({file_size} bytes). Minimum {MIN_FRAME_SIZE_BYTES} bytes.",
        )
    if file_size > MAX_FRAME_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Frame exceeds maximum allowed size of {MAX_FRAME_SIZE_BYTES // (1024*1024)} MB.",
        )

    # 4. Format validation via magic bytes
    detected_mime = detect_image_format(frame_bytes)
    if not detected_mime or detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported or invalid image format. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    # 5. In-memory Pillow integrity check (detect truncated/corrupt images)
    try:
        with Image.open(io.BytesIO(frame_bytes)) as img:
            img.verify()
            width, height = img.size
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed or corrupt image file.",
        ) from exc

    logger.info(
        "Phone camera frame received for vehicle %s: format=%s, dimensions=%dx%d, size=%.1f KB",
        vehicle_id,
        detected_mime,
        width,
        height,
        file_size / 1024.0,
    )

    result = process_frame(
        vehicle_id=vehicle_id,
        frame_bytes=frame_bytes,
        timestamp=now_ts,
        lat=lat,
        lng=lng,
        heading_deg=heading_deg,
    )

    msg = "Frame accepted and processed successfully" if result else "Frame accepted; lane detection not available"
    return FrameResponse(
        accepted=True,
        vehicle_id=vehicle_id,
        message=msg,
        result=result,
    )


@router.get("/api/camera/status")
async def get_camera_telemetry():
    """Retrieve telemetry, connection state, and lane detection metrics."""
    from camera_manager import get_camera_manager
    mgr = get_camera_manager()
    return mgr.get_status()


class CameraSourceRequest(BaseModel):
    source: Union[int, str] = Field(..., description="Camera source: 0, 1, or 'prerecorded'")
    vehicle_id: Optional[str] = "V001"


class CameraAccessRequest(BaseModel):
    enabled: bool = Field(..., description="True to turn camera ON, False to turn camera OFF and release hardware")
    source: Optional[Union[int, str]] = Field(default=None, description="Optional camera source: 0, 1, or 'prerecorded'")
    vehicle_id: Optional[str] = "V001"


@router.post("/api/camera/access")
@router.post("/api/camera/power")
async def toggle_camera_access(req: CameraAccessRequest):
    """Explicitly turn camera access ON or OFF.
    When OFF, immediately releases video capture handle and turns off physical camera LED."""
    from camera_manager import get_camera_manager
    mgr = get_camera_manager(vehicle_id=req.vehicle_id or "V001")
    if req.source is not None:
        mgr.set_source(req.source)

    if req.enabled:
        mgr.start()
        msg = f"Camera access ENABLED on source '{mgr.camera_source}'"
    else:
        mgr.stop()
        msg = "Camera access DISABLED. Hardware handle released."

    return {
        "status": "ok",
        "camera_enabled": mgr.camera_enabled,
        "is_connected": mgr.is_connected,
        "source": str(mgr.camera_source),
        "source_type": mgr.source_type,
        "message": msg,
    }


class CameraConfigRequest(BaseModel):
    capture_interval_s: Optional[float] = Field(default=None, ge=1.0, le=60.0, description="Interval in seconds between still photo captures (default 5.0s)")
    diagnostic_retention: Optional[bool] = Field(default=None, description="Explicit flag to temporarily store annotated diagnostic snapshots")


@router.post("/api/camera/capture")
async def trigger_manual_capture():
    """Trigger an immediate single still photo capture and ML analysis."""
    from camera_manager import get_camera_manager
    mgr = get_camera_manager()
    result = mgr.capture_single_photo()
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Photo capture failed: {mgr.last_error or 'CAMERA_UNAVAILABLE'}",
        )
    return {
        "status": "ok",
        "message": "Still photo captured and processed",
        "result": result,
        "telemetry": mgr.get_status(),
    }


@router.post("/api/camera/config")
async def update_camera_config(req: CameraConfigRequest):
    """Configure capture interval or diagnostic retention."""
    from camera_manager import get_camera_manager
    mgr = get_camera_manager()
    mgr.set_config(interval_s=req.capture_interval_s, diagnostic_retention=req.diagnostic_retention)
    return {
        "status": "ok",
        "capture_interval_s": mgr.capture_interval_s,
        "diagnostic_retention": mgr.diagnostic_retention,
    }


@router.post("/api/camera/source")
async def set_camera_source(req: CameraSourceRequest):
    """Switch camera source between physical USB camera and prerecorded test mode."""
    from camera_manager import get_camera_manager
    mgr = get_camera_manager(vehicle_id=req.vehicle_id or "V001")
    mgr.set_source(req.source)
    # Only start if camera access was already explicitly turned on by the user
    if mgr.camera_enabled and not mgr._running:
        mgr.start()
    return {
        "status": "ok",
        "source": str(req.source),
        "source_type": mgr.source_type,
        "camera_enabled": mgr.camera_enabled,
    }


@router.get("/api/camera/preview")
async def get_camera_preview():
    """Return latest annotated camera frame as JPEG image for HUD display."""
    from camera_manager import get_camera_manager
    from fastapi.responses import Response
    mgr = get_camera_manager()
    if mgr.camera_enabled and mgr.latest_frame_jpeg is not None:
        return Response(content=mgr.latest_frame_jpeg, media_type="image/jpeg")

    # Generate placeholder frame when camera access is disabled
    import cv2
    import numpy as np
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    blank[:, :] = (20, 24, 33)  # Slate dark bg
    cv2.putText(blank, "CAMERA ACCESS OFF", (35, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (100, 120, 160), 2)
    cv2.putText(blank, "Click 'TURN ON' to activate", (45, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 150, 170), 1)
    _, buf = cv2.imencode(".jpg", blank)
    return Response(content=buf.tobytes(), media_type="image/jpeg")