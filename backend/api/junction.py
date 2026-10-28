"""Lane-Aware Intelligent Emergency Vehicle Alert System
Junction Controller WebSocket & REST API Router.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from junction_service import get_junction_service

logger = logging.getLogger("backend.api.junction")

router = APIRouter(tags=["junction"])


@router.websocket("/ws/junction/{junction_id}")
async def junction_websocket(websocket: WebSocket, junction_id: str):
    """Authenticated WebSocket endpoint for physical Junction ESP32."""
    await websocket.accept()
    svc = get_junction_service()
    svc.register_socket(junction_id, websocket)

    # Send initial welcome & sync packet
    await websocket.send_json({
        "type": "welcome",
        "junction_id": junction_id,
        "message": "Connected to Lane-Aware Traffic Signal Controller Service",
    })

    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict):
                await svc.handle_junction_message(junction_id, data)
    except WebSocketDisconnect:
        logger.info("Junction ESP32 %s disconnected", junction_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Junction ESP32 %s error: %s", junction_id, exc)
    finally:
        svc.unregister_socket(junction_id, websocket)


@router.get("/api/junction/status")
async def get_all_junctions():
    """Retrieve all junction states, active priorities, and light aspects."""
    svc = get_junction_service()
    return svc.get_all_states()


class ManualPriorityTrigger(BaseModel):
    approach_id: str = "NORTH_SOUTH"
    eta_s: float = 15.0


@router.post("/api/junction/priority/{junction_id}")
async def trigger_manual_priority(junction_id: str, req: ManualPriorityTrigger):
    """Manually issue priority request for hardware test / bench demonstration."""
    import time
    from fastapi import HTTPException
    from models import AmbulanceState
    svc = get_junction_service()
    cfg = svc._configs.get(junction_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Unknown junction {junction_id}")

    valid_approaches = (cfg.emergency_approach, cfg.cross_approach, "CLEAR")
    if req.approach_id not in valid_approaches:
        raise HTTPException(status_code=400, detail=f"Invalid approach_id '{req.approach_id}'. Must be one of {valid_approaches}")

    # Simulate emergency vehicle approaching
    mock_amb = AmbulanceState(
        lat=cfg.lat - 0.002,  # ~220m south
        lng=cfg.lng,
        speed_kmh=50.0,
        heading_deg=0.0,
        emergency=True,
        ts=time.time(),
        ambulance_id="AMB_MANUAL",
    )
    await svc.evaluate_eta_and_trigger(mock_amb)
    return {"status": "priority_triggered", "junction_id": junction_id, "state": svc.get_state(junction_id)}


@router.post("/api/junction/report/{junction_id}")
async def report_junction_hardware_state(junction_id: str, payload: Dict[str, Any]):
    """Authenticated REST reporting endpoint for junction ESP32."""
    svc = get_junction_service()
    await svc.handle_junction_message(junction_id, payload)
    return {"status": "acknowledged", "junction_id": junction_id}


class JunctionConfigUpdate(BaseModel):
    eta_trigger_seconds: Optional[float] = None
    dist_trigger_meters: Optional[float] = None
    emergency_approach: Optional[str] = None


@router.post("/api/junction/config/{junction_id}")
async def update_junction_config(junction_id: str, req: JunctionConfigUpdate):
    """Update configurable priority trigger thresholds."""
    svc = get_junction_service()
    updated = svc.set_junction_config(
        junction_id,
        eta_trigger_seconds=req.eta_trigger_seconds,
        dist_trigger_meters=req.dist_trigger_meters,
        emergency_approach=req.emergency_approach,
    )
    if not updated:
        return {"status": "error", "message": f"Unknown junction {junction_id}"}
    return {"status": "ok", "config": updated.model_dump()}
