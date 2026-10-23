"""Lane-Aware Intelligent Emergency Vehicle Alert System
PHASE 4: Device Registration & Configuration REST Router.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status
from device_service import get_device_service
from models import (
    AmbulanceConfigRequest,
    DeviceRegisterRequest,
    DeviceRegistration,
)

logger = logging.getLogger("backend.api.device")

router = APIRouter(tags=["device"])


@router.post("/api/device/register", response_model=DeviceRegistration)
async def register_device(req: DeviceRegisterRequest) -> DeviceRegistration:
    """Register a new device or change role with role-based authorization."""
    dev_svc = get_device_service()
    return dev_svc.register_device(req)


@router.get("/api/device/list", response_model=List[DeviceRegistration])
async def list_devices() -> List[DeviceRegistration]:
    """Retrieve all registered vehicles and emergency devices."""
    dev_svc = get_device_service()
    return dev_svc.list_devices()


@router.get("/api/device/{device_id}", response_model=DeviceRegistration)
async def get_device(device_id: str) -> DeviceRegistration:
    """Lookup a registered device by unique ID."""
    dev_svc = get_device_service()
    dev = dev_svc.get_device(device_id)
    if dev is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' is not registered",
        )
    return dev


@router.post("/api/ambulance/config", response_model=DeviceRegistration)
async def update_ambulance_config(req: AmbulanceConfigRequest) -> DeviceRegistration:
    """Configure fixed intended lane and approach for the emergency vehicle."""
    dev_svc = get_device_service()
    return dev_svc.update_ambulance_config(req)


@router.get("/api/ambulance/config")
async def get_ambulance_config(ambulance_id: str = "AMB01") -> Dict[str, Any]:
    """Retrieve fixed intended lane and approach for the emergency vehicle."""
    dev_svc = get_device_service()
    return dev_svc.get_ambulance_config(ambulance_id)
