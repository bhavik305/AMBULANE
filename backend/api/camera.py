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

import io
import logging
import time
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, status
from pydantic import BaseModel, Field
from PIL import Image

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
    """Result of running lane detection on a camera frame."""

    vehicle_id: str = Field(..., description="Vehicle the frame belongs to")
    lane: Optional[str] = Field(
        default=None,
        description="Lane label: 'LEFT', 'CENTER', 'RIGHT'",
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
        default=None, description="Number of detected lane boundaries"
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
) -> Optional[LaneDetectionResult]:
    """Run the lane detection pipeline on a single validated frame."""
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

    proc_ms = round((time.time() - t0) * 1000.0, 1)
    res = LaneDetectionResult(
        vehicle_id=vehicle_id,
        lane=lane_info.get("lane"),
        lane_confidence=lane_info.get("lane_confidence"),
        timestamp=ts,
        processing_time_ms=proc_ms,
        detected_lanes_count=lane_info.get("detected_lanes_count", 0),
    )

    # Merge lane prediction into active vehicle state if vehicle is connected
    ws_mgr = get_ws_manager()
    v_state = ws_mgr.get_vehicle_state(vehicle_id)
    if v_state is not None and res.lane is not None:
        v_state.lane = res.lane
        v_state.lane_confidence = res.lane_confidence
        ws_mgr.set_vehicle_state(vehicle_id, v_state)
        logger.info("Updated vehicle %s lane state to %s (conf=%.2f)", vehicle_id, res.lane, res.lane_confidence or 0.0)

    return res


@router.post("/api/camera/frame/{vehicle_id}", response_model=FrameResponse)
async def upload_frame(
    vehicle_id: str,
    file: UploadFile = File(..., description="Camera frame image bytes"),
) -> FrameResponse:
    """Receive and validate camera frame from a participant vehicle."""
    ws_manager = get_ws_manager()
    if not ws_manager.has_vehicle(vehicle_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown vehicle_id '{vehicle_id}'. Vehicle must connect via WebSocket first.",
        )

    # 1. Read bytes in memory (no disk storage for privacy and security)
    frame_bytes = await file.read()
    file_size = len(frame_bytes)

    # 2. File size validation
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

    # 3. Format validation via magic bytes
    detected_mime = detect_image_format(frame_bytes)
    if not detected_mime or detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported or invalid image format. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    # 4. In-memory Pillow integrity check (detect truncated/corrupt images)
    try:
        with Image.open(io.BytesIO(frame_bytes)) as img:
            img.verify()
            width, height = img.size
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed or corrupt image file.",
        ) from exc

    # Log safe metadata only (no raw image data or sensitive content logged)
    logger.info(
        "Camera frame received for vehicle %s: format=%s, dimensions=%dx%d, size=%.1f KB",
        vehicle_id,
        detected_mime,
        width,
        height,
        file_size / 1024.0,
    )

    result = process_frame(
        vehicle_id=vehicle_id,
        frame_bytes=frame_bytes,
        timestamp=time.time(),
    )

    msg = "Frame accepted and processed successfully" if result else "Frame accepted; lane detection not available"
    return FrameResponse(
        accepted=True,
        vehicle_id=vehicle_id,
        message=msg,
        result=result,
    )