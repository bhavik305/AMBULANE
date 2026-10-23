"""Lane-Aware Intelligent Emergency Vehicle Alert System
PHASE 4: Device Registration, Role Management & Fixed Ambulance Configuration.

Rules:
- Explicit device roles: AMBULANCE vs NORMAL_VEHICLE.
- Role protection: Ordinary vehicles cannot claim AMBULANCE without authorized admin PIN.
- Ambulance lane and approach are fixed configuration values, NOT dynamically overwritten
  by uncertain single-camera observations.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from models import (
    AmbulanceConfigRequest,
    DeviceRegisterRequest,
    DeviceRegistration,
    DeviceRole,
)

logger = logging.getLogger("backend.device_service")

# Authorized PIN required to register or change an emergency vehicle role
AMBULANCE_ADMIN_PIN = os.environ.get("AMBULANCE_ADMIN_PIN", "9911")


class DeviceService:
    """Thread-safe registry for device roles, authorization tokens, and fixed lane configurations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._devices: Dict[str, DeviceRegistration] = {}

        # Pre-seed standard demonstration devices with grounded defaults
        t0 = time.time()
        self._devices["AMB01"] = DeviceRegistration(
            device_id="AMB01",
            role=DeviceRole.AMBULANCE,
            auth_token="AMB_SECURE_TOKEN_01",
            registered_at=t0,
            configured_lane="CENTER",
            configured_approach="NORTH_SOUTH",
            road_corridor_id="CORRIDOR_MG_ROAD",
        )
        self._devices["V001"] = DeviceRegistration(
            device_id="V001",
            role=DeviceRole.NORMAL_VEHICLE,
            auth_token="VEH_TOKEN_V001",
            registered_at=t0,
            configured_lane=None,
            configured_approach=None,
            road_corridor_id="CORRIDOR_MG_ROAD",
        )

    def register_device(self, req: DeviceRegisterRequest) -> DeviceRegistration:
        """Register a new device or reconfigure existing device with role verification."""
        with self._lock:
            # 1. Role Authorization Gate
            if req.role == DeviceRole.AMBULANCE:
                if req.admin_pin != AMBULANCE_ADMIN_PIN:
                    logger.warning(
                        "Unauthorized attempt to register AMBULANCE role for device '%s'", req.device_id
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Admin authorization required: Invalid PIN for AMBULANCE registration",
                    )

            # 2. Generate unique authorization token
            token = f"TOKEN_{req.role.value[:3]}_{uuid.uuid4().hex[:8]}"

            # 3. Create and store record
            reg = DeviceRegistration(
                device_id=req.device_id,
                role=req.role,
                auth_token=token,
                registered_at=time.time(),
                configured_lane=req.configured_lane if req.role == DeviceRole.AMBULANCE else None,
                configured_approach=req.configured_approach if req.role == DeviceRole.AMBULANCE else None,
                road_corridor_id="CORRIDOR_MG_ROAD",
            )
            self._devices[req.device_id] = reg
            logger.info("Device '%s' registered with role %s", req.device_id, req.role.value)
            return reg

    def get_device(self, device_id: str) -> Optional[DeviceRegistration]:
        """Lookup registration record for a device."""
        with self._lock:
            return self._devices.get(device_id)

    def list_devices(self) -> List[DeviceRegistration]:
        """Return list of all registered devices."""
        with self._lock:
            return list(self._devices.values())

    def update_ambulance_config(self, req: AmbulanceConfigRequest) -> DeviceRegistration:
        """Update the fixed designated lane and approach for an emergency vehicle."""
        with self._lock:
            dev = self._devices.get(req.ambulance_id)
            if dev is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Emergency device '{req.ambulance_id}' not found in registry",
                )
            if dev.role != DeviceRole.AMBULANCE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Device '{req.ambulance_id}' is registered as {dev.role.value}, not AMBULANCE",
                )

            # Optional token validation if provided
            if req.auth_token is not None and req.auth_token != dev.auth_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization token for ambulance configuration update",
                )

            dev.configured_lane = req.configured_lane.upper()
            if req.configured_approach:
                dev.configured_approach = req.configured_approach.upper()

            self._devices[req.ambulance_id] = dev
            logger.info(
                "Ambulance '%s' fixed configuration updated: lane=%s, approach=%s",
                req.ambulance_id,
                dev.configured_lane,
                dev.configured_approach,
            )
            return dev

    def get_ambulance_config(self, ambulance_id: str = "AMB01") -> Dict[str, Any]:
        """Return current fixed lane and approach configuration for ambulance."""
        dev = self.get_device(ambulance_id)
        if dev is None or dev.role != DeviceRole.AMBULANCE:
            return {
                "ambulance_id": ambulance_id,
                "configured_lane": "CENTER",
                "designated_lane": "CENTER",
                "configured_approach": "NORTH_SOUTH",
                "designated_approach": "NORTH_SOUTH",
                "is_registered": False,
            }
        return {
            "ambulance_id": dev.device_id,
            "configured_lane": dev.configured_lane or "CENTER",
            "designated_lane": dev.configured_lane or "CENTER",
            "configured_approach": dev.configured_approach or "NORTH_SOUTH",
            "designated_approach": dev.configured_approach or "NORTH_SOUTH",
            "road_corridor_id": dev.road_corridor_id,
            "registered_at": dev.registered_at,
            "is_registered": True,
        }


# Singleton accessor
_device_service: Optional[DeviceService] = None


def get_device_service() -> DeviceService:
    global _device_service
    if _device_service is None:
        _device_service = DeviceService()
    return _device_service
