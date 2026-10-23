"""Lane-Aware Intelligent Emergency Vehicle Alert System
Temporal Lane Tracking & State Estimator.

Maintains multi-frame temporal stability:
- Filters high-frequency jitter via Exponential Moving Average (EMA).
- Enforces state hysteresis to prevent single-frame lane classification flickering.
- Computes scene illumination metrics (detects night/tunnel/occlusion conditions).
- Generates continuous road path geometry for vehicle navigation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


class TemporalLaneTracker:
    """Temporal filter maintaining smooth vehicle lane and lateral offset estimates."""

    def __init__(
        self,
        alpha_offset: float = 0.60,
        confidence_decay: float = 0.85,
        min_confidence_threshold: float = 0.40,
        history_window: int = 5,
    ) -> None:
        self.alpha_offset = alpha_offset
        self.confidence_decay = confidence_decay
        self.min_confidence_threshold = min_confidence_threshold
        self.history_window = history_window

        # State memory
        self._smoothed_offset: Optional[float] = None
        self._current_lane: Optional[str] = None
        self._current_conf: float = 0.0
        self._last_update_ts: float = 0.0
        self._history_lanes: List[str] = []
        self._frame_count: int = 0

    def update(
        self,
        raw_lane: Optional[str],
        raw_offset_m: Optional[float],
        raw_conf: float,
        timestamp: Optional[float] = None,
        scene_brightness: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update tracker state with new frame estimation and return smoothed output."""
        now = timestamp or time.time()
        self._frame_count += 1

        dt = now - self._last_update_ts if self._last_update_ts > 0 else 0.1
        self._last_update_ts = now

        # In photo-only mode (e.g. 5s interval), reset historical smoothing window
        # so each still image is evaluated strictly on its own current visual evidence
        if dt > 3.0:
            self._history_lanes.clear()
            self._smoothed_offset = None

        # 1. Illumination condition assessment
        lighting_condition = "NORMAL"
        if scene_brightness is not None:
            if scene_brightness < 35.0:
                lighting_condition = "LOW_LIGHT_OR_NIGHT"
            elif scene_brightness > 225.0:
                lighting_condition = "GLARE_OR_OVEREXPOSURE"

        # 2. Confidence evaluation & decay
        if raw_lane is None or raw_conf < self.min_confidence_threshold:
            self._current_conf *= self.confidence_decay
            if self._current_conf < self.min_confidence_threshold or raw_lane is None:
                self._current_lane = None
                self._current_conf = 0.0
                self._smoothed_offset = None
            return {
                "lane": self._current_lane,
                "lane_confidence": round(self._current_conf, 2),
                "lateral_offset_m": self._smoothed_offset,
                "status": "uncertain_or_lost",
                "lighting_condition": lighting_condition,
                "frame_count": self._frame_count,
                "timestamp": now,
            }

        # 3. Temporal smoothing for lateral offset (meters)
        if raw_offset_m is not None:
            if self._smoothed_offset is None:
                self._smoothed_offset = round(raw_offset_m, 2)
            else:
                self._smoothed_offset = round(
                    self.alpha_offset * raw_offset_m + (1.0 - self.alpha_offset) * self._smoothed_offset,
                    2,
                )

        # 4. Multi-frame majority voting for lane category (anti-flicker hysteresis)
        self._history_lanes.append(raw_lane)
        if len(self._history_lanes) > self.history_window:
            self._history_lanes.pop(0)

        # Determine dominant lane in history window
        lane_counts: Dict[str, int] = {}
        for l in self._history_lanes:
            lane_counts[l] = lane_counts.get(l, 0) + 1

        dominant_lane = max(lane_counts, key=lane_counts.get)
        # Require at least 60% agreement in window to switch
        if lane_counts[dominant_lane] >= int(0.6 * len(self._history_lanes)):
            self._current_lane = dominant_lane

        self._current_conf = round(raw_conf, 2)

        # 5. Compute road path geometry polyline
        # Coordinates in vehicle-centric relative space (meters ahead: Y, meters lateral: X)
        curv_offset = self._smoothed_offset or 0.0
        path_geometry = [
            {"x_m": round(curv_offset, 2), "y_m": 0.0},
            {"x_m": round(curv_offset * 0.8, 2), "y_m": 10.0},
            {"x_m": round(curv_offset * 0.5, 2), "y_m": 25.0},
            {"x_m": 0.0, "y_m": 45.0},
        ]

        return {
            "lane": self._current_lane,
            "lane_confidence": self._current_conf,
            "lateral_offset_m": self._smoothed_offset,
            "status": "tracking_active",
            "lighting_condition": lighting_condition,
            "path_geometry": path_geometry,
            "frame_count": self._frame_count,
            "timestamp": now,
        }

    def reset(self) -> None:
        """Reset internal filter states."""
        self._smoothed_offset = None
        self._current_lane = None
        self._current_conf = 0.0
        self._history_lanes.clear()
        self._frame_count = 0
