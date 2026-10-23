"""Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 8 — Genuine ML Model Management and Neural Inference Engine.

Integrates LaneFeatureNet (PyTorch) with CPU/CUDA inference:
- Loads trained weights from ai/weights/lane_model.pt (or TorchScript).
- Runs forward inference with torch.no_grad().
- Measures actual inference latency in milliseconds.
- Outputs structured classification (LEFT, CENTER, RIGHT), lateral offset in meters,
  and visibility confidence score.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional
import cv2
import numpy as np

logger = logging.getLogger("backend.ai.lane_model")


class LaneDetectionModel:
    """Base interface for lane detection inference."""

    def __init__(self, model_path: Optional[str] = None) -> None:
        self.model_path = model_path
        self._loaded = False
        self.backend_type = "none"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> bool:
        """Attempt to load model weights from disk. Returns True if successfully loaded."""
        raise NotImplementedError("Subclasses must implement load()")

    def detect(self, preprocessed_frame: np.ndarray) -> Dict[str, Any]:
        """Run model inference on a preprocessed image frame."""
        raise NotImplementedError("Subclasses must implement detect()")


class DeepLearningLaneModel(LaneDetectionModel):
    """Production PyTorch neural network lane model loader and inference engine."""

    def __init__(self, model_path: Optional[str] = None) -> None:
        default_path = os.path.join(os.path.dirname(__file__), "weights", "lane_model.pt")
        super().__init__(model_path=model_path or default_path)
        self.model = None
        self._device = "cpu"

    def load(self) -> bool:
        if not self.model_path or not os.path.isfile(self.model_path):
            logger.info(
                "No deep-learning lane weights found at '%s'. Classical CV active.",
                self.model_path,
            )
            self._loaded = False
            self.backend_type = "unloaded_scaffold"
            return False

        try:
            import torch

            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("Initializing lane model on device: %s", self._device)

            script_path = os.path.join(os.path.dirname(self.model_path), "lane_model_scripted.pt")
            if os.path.isfile(script_path):
                self.model = torch.jit.load(script_path, map_location=self._device)
                self.model.eval()
                self._loaded = True
                self.backend_type = "pytorch_torchscript"
                logger.info("TorchScript lane model loaded successfully from %s", script_path)
                return True

            from ai.model_def import LaneFeatureNet
            net = LaneFeatureNet()
            state_dict = torch.load(self.model_path, map_location=self._device)
            net.load_state_dict(state_dict)
            net.to(self._device)
            net.eval()
            self.model = net
            self._loaded = True
            self.backend_type = "pytorch_torchscript"
            logger.info("LaneFeatureNet weights loaded successfully from %s", self.model_path)
            return True
        except Exception as exc:  # noqa: BLE001
            # Try TorchScript fallback if state_dict fails
            try:
                import torch
                script_path = os.path.join(os.path.dirname(self.model_path), "lane_model_scripted.pt")
                if os.path.isfile(script_path):
                    self.model = torch.jit.load(script_path, map_location=self._device)
                    self.model.eval()
                    self._loaded = True
                    self.backend_type = "pytorch_torchscript"
                    logger.info("TorchScript lane model loaded successfully.")
                    return True
            except Exception:
                pass

            logger.warning("Failed to load model from %s: %s", self.model_path, exc)
            self._loaded = False
            self.backend_type = "load_error"
            return False

    def detect(self, preprocessed_frame: np.ndarray) -> Dict[str, Any]:
        """Execute forward neural inference on an input frame."""
        if not self._loaded or self.model is None:
            return {
                "lane": None,
                "lane_confidence": 0.0,
                "lateral_offset_m": 0.0,
                "detected_lanes_count": 0,
                "latency_ms": 0.0,
                "model_type": "none",
                "status": "model_not_loaded",
            }

        import torch

        t0 = time.time()
        h, w = preprocessed_frame.shape[:2]

        # Resize to network input shape (180, 320)
        resized = cv2.resize(preprocessed_frame, (320, 180), interpolation=cv2.INTER_LINEAR)
        # Convert BGR -> RGB and normalize to [0, 1]
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = torch.tensor(rgb, dtype=torch.float32, device=self._device).permute(2, 0, 1).unsqueeze(0) / 255.0

        with torch.no_grad():
            lane_logits, offset_pred, conf_pred = self.model(tensor)

        latency_ms = round((time.time() - t0) * 1000.0, 2)

        # Interpret logits
        probs = torch.softmax(lane_logits, dim=1).cpu().numpy()[0]
        class_idx = int(np.argmax(probs))
        class_map = {0: "LEFT", 1: "CENTER", 2: "RIGHT"}
        predicted_lane = class_map.get(class_idx, "CENTER")

        # Scaled lateral offset in meters (standard lane ~3.5m, half-lane ~1.75m)
        raw_offset = float(offset_pred.cpu().item())
        lateral_offset_m = round(raw_offset * 1.75, 2)

        confidence = round(float(conf_pred.cpu().item() * probs[class_idx]), 2)

        return {
            "lane": predicted_lane,
            "lane_confidence": confidence,
            "lateral_offset_m": lateral_offset_m,
            "detected_lanes_count": 2 if confidence >= 0.50 else 1,
            "latency_ms": latency_ms,
            "model_type": "pytorch_lane_net",
            "status": "inference_ok",
        }


def load_model(model_path: Optional[str] = None) -> LaneDetectionModel:
    """Factory creating and initializing the lane detection model."""
    model = DeepLearningLaneModel(model_path=model_path)
    model.load()
    return model