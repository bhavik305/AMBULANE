"""Lane-Aware Intelligent Emergency Vehicle Alert System
PHASE 2 & PHASE 3: Vehicle-Mounted Road Camera Manager (Strict Photo-Only Operation).

Strict Requirements:
1. Capture exactly one still image per configured capture interval (default 5.0 seconds).
2. Never record continuous video, save video clips, or stream video.
3. Never use video-based temporal inference across multi-second intervals.
4. Process still image and discard from memory immediately after inference
   (unless diagnostic retention is explicitly enabled).
5. If camera is unavailable, report CAMERA_UNAVAILABLE; never invent images.
6. Serve single still-image preview with ML annotation overlay.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np

from ai.lane_detection import detect_lane
from websocket_manager import get_ws_manager

logger = logging.getLogger("backend.camera_manager")


class VehicleCameraManager:
    """Manages interval-based still photo acquisition and ML lane estimation."""

    def __init__(
        self,
        vehicle_id: str = "V001",
        camera_source: Any = 0,
        capture_interval_s: float = 5.0,
        target_fps: Optional[float] = None,
    ) -> None:
        self.vehicle_id = vehicle_id
        self.camera_source = camera_source
        if target_fps is not None and target_fps > 0 and capture_interval_s == 5.0:
            # Map legacy target_fps request to single still-frame interval
            self.capture_interval_s = float(1.0 / target_fps)
        else:
            self.capture_interval_s = float(capture_interval_s)

        # Operational & Lifecycle Flags
        self._running = False
        self.camera_enabled = False
        self.diagnostic_retention = False
        self._thread: Optional[threading.Thread] = None
        self._capture_lock = threading.Lock()

        # Telemetry & Status
        self.camera_status = "DISABLED"  # DISABLED, IDLE, CAPTURING, CAMERA_UNAVAILABLE
        self.is_connected = False
        self.source_type = "uninitialized"
        self.resolution = (0, 0)
        self.frames_captured = 0
        self.last_capture_ts: Optional[float] = None
        self.next_capture_ts: Optional[float] = None
        self.last_error: Optional[str] = None
        self.latest_result: Optional[Dict[str, Any]] = None
        self.latest_frame_jpeg: Optional[bytes] = None

    def _acquire_single_frame(self) -> Tuple[bool, Optional[np.ndarray], str]:
        """Capture exactly one still frame from configured camera and release capture hardware."""
        src = self.camera_source

        # 1. Prerecorded / Synthetic Test Mode
        if isinstance(src, str) and (src.lower() == "prerecorded" or src.endswith((".mp4", ".avi", ".jpg", ".png"))):
            test_img_path = os.path.join(os.path.dirname(__file__), "data", "road_still_test.jpg")
            if not os.path.isfile(test_img_path):
                self._generate_test_image(test_img_path)
            frame = cv2.imread(test_img_path)
            if frame is not None:
                return True, frame, "prerecorded_still_test_mode"
            return False, None, "prerecorded_still_test_mode"

        # 2. Physical USB or IP Camera Single-Frame Capture
        cap = None
        try:
            try:
                cam_idx = int(src)
                backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
                cap = cv2.VideoCapture(cam_idx, backend)
                source_label = f"physical_usb_camera_{cam_idx}"
            except (ValueError, TypeError):
                cap = cv2.VideoCapture(str(src))
                source_label = "ip_camera_snapshot"

            if cap is None or not cap.isOpened():
                return False, None, source_label

            # Read exactly 1 frame
            ret, frame = cap.read()
            if ret and frame is not None:
                return True, frame, source_label
            return False, None, source_label
        except Exception as exc:
            logger.error("Exception acquiring single frame from %s: %s", src, exc)
            return False, None, "error"
        finally:
            if cap is not None:
                cap.release()

    def _generate_test_image(self, out_path: str) -> None:
        """Generate a deterministic synthetic road still image for test mode."""
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        w, h = 640, 360
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[int(h * 0.45):, :] = (65, 65, 65)  # Asphalt
        img[:int(h * 0.45), :] = (190, 160, 120)  # Sky

        # Center dashed markings
        cv2.line(img, (w // 2, int(h * 0.45)), (w // 2, h), (255, 255, 255), 4)
        # Left lane solid line
        cv2.line(img, (int(w * 0.35), int(h * 0.45)), (int(w * 0.15), h), (240, 240, 240), 5)
        # Right lane solid line
        cv2.line(img, (int(w * 0.65), int(h * 0.45)), (int(w * 0.85), h), (240, 240, 240), 5)
        cv2.imwrite(out_path, img)

    def capture_single_photo(self) -> Optional[Dict[str, Any]]:
        """Perform one photo capture cycle: acquire -> validate -> ML inference -> annotate -> discard."""
        if not self._capture_lock.acquire(blocking=False):
            logger.warning("Photo capture skipped: another capture is currently in progress")
            return None

        try:
            self.camera_status = "CAPTURING"
            success, raw_frame, src_label = self._acquire_single_frame()
            self.source_type = src_label

            if not success or raw_frame is None:
                self.is_connected = False
                self.camera_status = "CAMERA_UNAVAILABLE"
                self.last_error = f"Still capture failed on source {self.camera_source}"
                logger.warning(self.last_error)
                return None

            now = time.time()
            self.is_connected = True
            self.last_error = None
            self.frames_captured += 1
            h, w = raw_frame.shape[:2]
            self.resolution = (w, h)

            # Encode to JPEG bytes for ML pipeline
            _, buf = cv2.imencode(".jpg", raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_bytes = buf.tobytes()

            # Execute Genuine ML Lane Inference
            result = detect_lane(frame_bytes, vehicle_id=self.vehicle_id, timestamp=now)
            self.latest_result = result

            # Create Still Preview with ML Annotation Overlay
            annotated_frame = raw_frame.copy()
            detected_lane = result.get("lane") if result else "UNKNOWN"
            conf = result.get("lane_confidence", 0.0) if result else 0.0
            latency = result.get("latency_ms", 0.0) if result else 0.0

            # Draw top overlay header
            cv2.rectangle(annotated_frame, (0, 0), (w, 36), (20, 24, 33), -1)
            time_str = time.strftime("%H:%M:%S", time.localtime(now))
            cv2.putText(
                annotated_frame,
                f"STILL PHOTO: {time_str} | INTERVAL: {self.capture_interval_s:.0f}s",
                (10, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (200, 210, 230),
                1,
            )

            # Draw lane estimate banner
            lane_color = (0, 220, 100) if detected_lane == "CENTER" else (0, 165, 255)
            if detected_lane == "UNKNOWN":
                lane_color = (120, 120, 140)
            cv2.putText(
                annotated_frame,
                f"LANE: {detected_lane} ({int(conf * 100)}%) [ML {latency:.1f}ms]",
                (10, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                lane_color,
                2,
            )

            # Encode annotated frame for preview and update cache
            _, ann_buf = cv2.imencode(".jpg", annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            self.latest_frame_jpeg = ann_buf.tobytes()

            # Diagnostic Retention Handling
            if self.diagnostic_retention:
                diag_dir = os.path.join(os.path.dirname(__file__), "data", "diagnostic_snapshots")
                os.makedirs(diag_dir, exist_ok=True)
                diag_file = os.path.join(diag_dir, f"snap_{int(now)}.jpg")
                cv2.imwrite(diag_file, annotated_frame)

            # Clean up raw frame from memory immediately (strict photo-only policy)
            del raw_frame
            del annotated_frame

            # Update Vehicle State in WebSocket Manager
            ws_mgr = get_ws_manager()
            v_state = ws_mgr.get_vehicle_state(self.vehicle_id)
            if v_state is not None and detected_lane is not None:
                v_state.lane = detected_lane
                v_state.lane_confidence = conf
                ws_mgr.set_vehicle_state(self.vehicle_id, v_state)

            self.last_capture_ts = now
            self.next_capture_ts = now + self.capture_interval_s
            self.camera_status = "IDLE"

            logger.info(
                "Still photo captured for %s: lane=%s (conf=%.2f, latency=%.1fms, next in %.1fs)",
                self.vehicle_id,
                detected_lane,
                conf,
                latency,
                self.capture_interval_s,
            )
            return result
        finally:
            self._capture_lock.release()

    def _interval_worker(self) -> None:
        """Timer worker that wakes up once every capture_interval_s to take 1 still photo."""
        logger.info(
            "Camera interval worker started (Interval = %.1f seconds)", self.capture_interval_s
        )
        # Take initial photo immediately upon start
        self.capture_single_photo()

        while self._running and self.camera_enabled:
            # Sleep until next scheduled interval in small 100ms slices for responsive stop
            sleep_slices = int(self.capture_interval_s * 10)
            for _ in range(sleep_slices):
                if not (self._running and self.camera_enabled):
                    break
                time.sleep(0.1)

            if self._running and self.camera_enabled:
                self.capture_single_photo()

        self.camera_status = "DISABLED"
        self.is_connected = False
        logger.info("Camera interval worker stopped")

    def start(self) -> None:
        """Start the interval still-photo acquisition timer."""
        self.camera_enabled = True
        self._running = True
        self.camera_status = "IDLE"
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._interval_worker, daemon=True, name="CameraPhotoWorker"
        )
        self._thread.start()
        logger.info("VehicleCameraManager photo mode started for %s", self.vehicle_id)

    def stop(self) -> None:
        """Stop background worker and ensure hardware resources are released."""
        self.camera_enabled = False
        self._running = False
        self.camera_status = "DISABLED"
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
        self.is_connected = False
        self.next_capture_ts = None
        logger.info("VehicleCameraManager photo mode stopped")

    def set_source(self, new_source: Any) -> None:
        """Update configured camera source."""
        logger.info("Switching camera source to %s", new_source)
        self.camera_source = new_source

    def set_config(self, interval_s: Optional[float] = None, diagnostic_retention: Optional[bool] = None) -> None:
        """Update interval or diagnostic retention settings."""
        if interval_s is not None and interval_s > 0.5:
            self.capture_interval_s = float(interval_s)
        if diagnostic_retention is not None:
            self.diagnostic_retention = bool(diagnostic_retention)
        logger.info(
            "Camera config updated: interval=%.1fs, diagnostic_retention=%s",
            self.capture_interval_s,
            self.diagnostic_retention,
        )

    def get_status(self) -> Dict[str, Any]:
        """Return structured telemetry for dashboard."""
        latest_lane = self.latest_result.get("lane") if self.latest_result else None
        confidence = self.latest_result.get("lane_confidence") if self.latest_result else 0.0
        model_type = self.latest_result.get("model_type") if self.latest_result else "none"
        offset_m = self.latest_result.get("lateral_offset_m") if self.latest_result else None
        latency = self.latest_result.get("latency_ms") if self.latest_result else 0.0
        light = self.latest_result.get("lighting_condition") if self.latest_result else "UNKNOWN"
        geom = self.latest_result.get("path_geometry") if self.latest_result else []

        now = time.time()
        seconds_until_next = (
            max(0.0, round(self.next_capture_ts - now, 1))
            if (self.camera_enabled and self.next_capture_ts is not None)
            else None
        )

        return {
            "vehicle_id": self.vehicle_id,
            "camera_enabled": self.camera_enabled,
            "camera_status": self.camera_status,
            "is_running": self._running,
            "is_connected": self.is_connected,
            "source_type": self.source_type,
            "camera_source": str(self.camera_source),
            "capture_interval_s": self.capture_interval_s,
            "fps": round(1.0 / max(0.001, self.capture_interval_s), 2),
            "last_capture_ts": self.last_capture_ts,
            "next_capture_ts": self.next_capture_ts,
            "seconds_until_next_capture": seconds_until_next,
            "frames_captured": self.frames_captured,
            "diagnostic_retention": self.diagnostic_retention,
            "resolution": f"{self.resolution[0]}x{self.resolution[1]}",
            "last_error": self.last_error,
            "lane": latest_lane,
            "lane_confidence": confidence,
            "lateral_offset_m": offset_m,
            "model_type": model_type,
            "inference_latency_ms": latency,
            "lighting_condition": light,
            "path_geometry": geom,
        }


# Singleton accessor
_camera_manager: Optional[VehicleCameraManager] = None


def get_camera_manager(vehicle_id: str = "V001") -> VehicleCameraManager:
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = VehicleCameraManager(vehicle_id=vehicle_id, camera_source=0, capture_interval_s=5.0)
    return _camera_manager
