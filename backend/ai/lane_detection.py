"""Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 8 — Lane and Path Detection Engine

Implementation:
----------------
This module provides a robust, production-grade Computer Vision lane detection pipeline:
1. Color Filtering: Isolates white and yellow lane markings in HLS / HSV color spaces.
2. Edge Detection: Computes Canny gradients on the filtered road surface.
3. Region of Interest: Applies trapezoidal drivable area masking.
4. Line Fitting: Performs Hough line detection and slope-based left/right boundary separation.
5. Lateral Position Estimation:
   - Evaluates the host vehicle's center (bottom center of image) against the lane center.
   - Computes lateral displacement offset.
   - Classifies host vehicle position: 'CENTER', 'LEFT', or 'RIGHT'.
6. Visual Overlay: Generates a visual overlay showing detected lane boundaries,
   corridor filling, and navigation HUD.

Limitations & Accuracy Disclosure:
-----------------------------------
- Camera field of view must capture painted or visible road boundaries.
- Lane classification (LEFT / CENTER / RIGHT) is relative to the camera view and the
  immediate lane corridor, NOT a global satellite coordinate.
- Ordinary single-frequency GPS (NEO-6M / Phone GPS, 3-5m error) cannot determine which lane
  a car occupies. This camera pipeline supplies that missing lateral lane resolution.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

from ai.preprocessing import extract_road_roi, preprocess_frame

logger = logging.getLogger("backend.ai.lane_detection")


def _filter_lane_colors(bgr: np.ndarray) -> np.ndarray:
    """Isolate white and yellow lane markings using HLS and HSV thresholds."""
    hls = cv2.cvtColor(bgr, cv2.COLOR_BGR2HLS)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

    # White lane marks: high lightness in HLS
    white_mask = cv2.inRange(hls, np.array([0, 180, 0]), np.array([255, 255, 255]))

    # Yellow lane marks: hue ~15-35, moderate saturation
    yellow_mask = cv2.inRange(hsv, np.array([15, 60, 100]), np.array([35, 255, 255]))

    combined_mask = cv2.bitwise_or(white_mask, yellow_mask)
    return combined_mask


def _fit_lane_lines(
    lines: np.ndarray, height: int, width: int
) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[Tuple[int, int, int, int]]]:
    """Separate Hough lines into left and right lane boundaries based on slope."""
    left_points: List[Tuple[int, int]] = []
    right_points: List[Tuple[int, int]] = []

    y_min = int(height * 0.60)
    y_max = height

    for line in lines:
        for x1, y1, x2, y2 in line:
            if x2 == x1:
                continue
            slope = (y2 - y1) / float(x2 - x1)
            # Filter near-horizontal noise lines
            if abs(slope) < 0.35 or abs(slope) > 2.5:
                continue

            # Left lane has negative slope in image coordinates (origin top-left)
            # and is located on the left half of the frame
            if slope < 0 and x1 < width * 0.55 and x2 < width * 0.55:
                left_points.extend([(x1, y1), (x2, y2)])
            # Right lane has positive slope and is on the right half of the frame
            elif slope > 0 and x1 > width * 0.45 and x2 > width * 0.45:
                right_points.extend([(x1, y1), (x2, y2)])

    left_line = None
    if len(left_points) >= 2:
        pts = np.array(left_points)
        vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
        if abs(vy) > 1e-4:
            x_bottom = int(x0 + (y_max - y0) * (vx / vy))
            x_top = int(x0 + (y_min - y0) * (vx / vy))
            left_line = (x_bottom, y_max, x_top, y_min)

    right_line = None
    if len(right_points) >= 2:
        pts = np.array(right_points)
        vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
        if abs(vy) > 1e-4:
            x_bottom = int(x0 + (y_max - y0) * (vx / vy))
            x_top = int(x0 + (y_min - y0) * (vx / vy))
            right_line = (x_bottom, y_max, x_top, y_min)

    return left_line, right_line


def generate_lane_overlay(
    image: np.ndarray,
    left_line: Optional[Tuple[int, int, int, int]],
    right_line: Optional[Tuple[int, int, int, int]],
    lane_label: Optional[str],
    confidence: float,
) -> np.ndarray:
    """Create visual overlay highlighting detected lane and HUD."""
    overlay = image.copy()
    h, w = image.shape[:2]

    # Draw lane corridor polygon if both lines are detected
    if left_line and right_line:
        poly_pts = np.array(
            [
                [left_line[0], left_line[1]],
                [left_line[2], left_line[3]],
                [right_line[2], right_line[3]],
                [right_line[0], right_line[1]],
            ],
            dtype=np.int32,
        )
        corridor_mask = np.zeros_like(image)
        # Green drivable corridor fill
        cv2.fillPoly(corridor_mask, [poly_pts], (0, 180, 0))
        overlay = cv2.addWeighted(overlay, 1.0, corridor_mask, 0.35, 0)

        # Draw left and right boundaries (yellow and blue)
        cv2.line(overlay, (left_line[0], left_line[1]), (left_line[2], left_line[3]), (0, 255, 255), 4)
        cv2.line(overlay, (right_line[0], right_line[1]), (right_line[2], right_line[3]), (255, 200, 0), 4)

    # Vehicle centerline vs Lane centerline markers
    veh_center_x = w // 2
    cv2.circle(overlay, (veh_center_x, h - 25), 8, (0, 0, 255), -1)

    # HUD Text Overlay
    hud_text = f"LANE: {lane_label or 'UNKNOWN'} (Conf: {confidence:.2f})"
    cv2.rectangle(overlay, (10, 10), (380, 50), (0, 0, 0), -1)
    color = (0, 255, 0) if lane_label == "CENTER" else (0, 165, 255)
    cv2.putText(overlay, hud_text, (20, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    return overlay


def detect_lane(
    frame_bytes: bytes,
    vehicle_id: str,
    timestamp: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Run the complete lane and path detection pipeline on a camera frame.

    Args:
        frame_bytes: Raw JPEG/PNG image bytes.
        vehicle_id: Associated vehicle identifier.
        timestamp: Capture or arrival timestamp.

    Returns:
        Structured result dict containing:
        - lane: 'CENTER', 'LEFT', 'RIGHT', or None
        - lane_confidence: float [0..1]
        - lateral_offset_m: estimated meters from lane center
        - detected_lanes_count: number of boundaries identified
        - timestamp: Unix timestamp
    """
    ts = timestamp or time.time()
    bgr, preprocessed = preprocess_frame(frame_bytes, target_size=(640, 360))
    if preprocessed is None:
        logger.warning("Frame preprocessing failed for vehicle %s", vehicle_id)
        return None

    h, w = preprocessed.shape[:2]

    # 1. Color extraction for road paint
    color_mask = _filter_lane_colors(preprocessed)

    # 2. Edge detection
    blurred = cv2.GaussianBlur(color_mask, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    roi_edges = extract_road_roi(edges)

    # 3. Hough Line Transform
    lines = cv2.HoughLinesP(
        roi_edges,
        rho=1,
        theta=np.pi / 180,
        threshold=25,
        minLineLength=30,
        maxLineGap=20,
    )

    if lines is None or len(lines) == 0:
        return {
            "vehicle_id": vehicle_id,
            "lane": None,
            "lane_confidence": 0.0,
            "lateral_offset_m": None,
            "detected_lanes_count": 0,
            "timestamp": ts,
            "model_type": "cv_lane_detector",
        }

    left_line, right_line = _fit_lane_lines(lines, h, w)
    detected_count = (1 if left_line else 0) + (1 if right_line else 0)

    if detected_count == 0:
        return {
            "vehicle_id": vehicle_id,
            "lane": None,
            "lane_confidence": 0.0,
            "lateral_offset_m": None,
            "detected_lanes_count": 0,
            "timestamp": ts,
            "model_type": "cv_lane_detector",
        }

    # 4. Lateral Position and Lane Classification
    veh_center_x = w / 2.0
    lane_width_px = w * 0.45  # Default estimated lane pixel width

    if left_line and right_line:
        left_base_x = left_line[0]
        right_base_x = right_line[0]
        actual_lane_width = max(100.0, float(right_base_x - left_base_x))
        lane_center_x = (left_base_x + right_base_x) / 2.0
        confidence = 0.85
    elif left_line:
        # Only left boundary visible; extrapolate lane center
        left_base_x = left_line[0]
        lane_center_x = left_base_x + (lane_width_px / 2.0)
        confidence = 0.55
    else:
        # Only right boundary visible; extrapolate lane center
        right_base_x = right_line[0]
        lane_center_x = right_base_x - (lane_width_px / 2.0)
        confidence = 0.55

    # Lateral pixel offset (positive = vehicle is to the right of lane center)
    offset_px = veh_center_x - lane_center_x
    normalized_offset = offset_px / (lane_width_px / 2.0)

    # Approximate pixel-to-meter conversion (standard lane ~ 3.5m)
    meters_per_pixel = 3.5 / lane_width_px
    lateral_offset_m = round(offset_px * meters_per_pixel, 2)

    # Explicit documented lane categorization:
    # - Within [-0.25, 0.25] of lane width -> CENTER
    # - Negative offset (< -0.25) -> LEFT
    # - Positive offset (> 0.25) -> RIGHT
    if abs(normalized_offset) <= 0.25:
        lane_label = "CENTER"
    elif normalized_offset < -0.25:
        lane_label = "LEFT"
    else:
        lane_label = "RIGHT"

    return {
        "vehicle_id": vehicle_id,
        "lane": lane_label,
        "lane_confidence": round(confidence, 2),
        "lateral_offset_m": lateral_offset_m,
        "detected_lanes_count": detected_count,
        "timestamp": ts,
        "model_type": "cv_lane_detector",
    }