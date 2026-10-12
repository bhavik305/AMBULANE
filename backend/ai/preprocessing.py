"""Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 8 — Frame Preprocessing Module

Responsibilities:
- In-memory decoding of raw camera frames (JPEG/PNG/WebP) to NumPy arrays.
- Resizing, color-space conversion, and normalization.
- Drivable roadway Region-Of-Interest (ROI) masking.
"""

from __future__ import annotations

import io
import logging
from typing import Optional, Tuple
import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("backend.ai.preprocessing")


def decode_frame(frame_bytes: bytes) -> Optional[np.ndarray]:
    """Decode raw image bytes into a BGR NumPy array (OpenCV format).

    Safe in-memory operation. Returns None if decoding fails.
    """
    if not frame_bytes or len(frame_bytes) < 100:
        return None

    # Fast OpenCV in-memory decode
    nparr = np.frombuffer(frame_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is not None:
        return img

    # Fallback to Pillow in case cv2 fails on certain WebP/PNG variants
    try:
        pil_img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
        rgb = np.array(pil_img)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to decode frame bytes: %s", exc)
        return None


def extract_road_roi(image: np.ndarray) -> np.ndarray:
    """Mask the upper half of the image (sky, buildings) to isolate the road roadway."""
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    # Trapezoid polygon focusing on forward driving lane:
    # Top vertices: 35% and 65% of width at 55% height
    # Bottom vertices: 5% and 95% of width at 100% height
    roi_poly = np.array(
        [
            [
                (int(w * 0.05), h),
                (int(w * 0.38), int(h * 0.55)),
                (int(w * 0.62), int(h * 0.55)),
                (int(w * 0.95), h),
            ]
        ],
        dtype=np.int32,
    )
    cv2.fillPoly(mask, roi_poly, 255)
    return cv2.bitwise_and(image, image, mask=mask)


def preprocess_frame(
    frame_bytes: bytes,
    target_size: Tuple[int, int] = (640, 360),
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Decode, resize, and isolate road ROI.

    Returns:
        (bgr_original, bgr_preprocessed) or (None, None) on failure.
    """
    bgr = decode_frame(frame_bytes)
    if bgr is None:
        return None, None

    # Resize while preserving aspect ratio if necessary
    resized = cv2.resize(bgr, target_size, interpolation=cv2.INTER_AREA)
    roi_masked = extract_road_roi(resized)

    return bgr, roi_masked