"""
Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 1 — Backend Foundation + Real-Time Communication

api/vehicle.py
==============
WebSocket endpoint for participant vehicles (phone app).

Endpoint:
    WS /ws/vehicle/{vehicle_id}

Flow (STEP 1):
    1. Vehicle connects with a vehicle_id -> registered in the manager.
    2. Valid telemetry message arrives -> validated, stored as the
       vehicle's latest state, made available to /status.
    3. Invalid telemetry -> logged, error sent back to the client,
       server does NOT crash.
    4. Disconnect -> vehicle is removed cleanly.

Backward compatibility:
    The current phone app may ONLY send lat/lng. The VehicleTelemetry
    model therefore makes speed_kmh, heading_deg, lane and
    lane_confidence OPTIONAL. We NEVER fabricate lane values.

Future steps connect here:
    - STEP 2: the matching engine will consume VehicleState together
      with the ambulance state and route corridor.
    - STEP 3: the camera API (api/camera.py) will feed lane detection
      results into VehicleState before the matching engine runs.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models import VehicleState, VehicleTelemetry
from websocket_manager import get_ws_manager

logger = logging.getLogger("backend.api.vehicle")

router = APIRouter(tags=["vehicle"])


def _serialize_state(state: VehicleState) -> Dict[str, Any]:
    """Convert a VehicleState to a plain JSON-serialisable dict."""
    return state.model_dump()


async def _handle_telemetry(vehicle_id: str, websocket: WebSocket, raw: Any) -> None:
    """Validate an incoming telemetry message and update vehicle state."""
    ws_manager = get_ws_manager()

    # --- 1. Validate -----------------------------------------------------
    try:
        telemetry = VehicleTelemetry.model_validate(raw)
    except ValidationError as exc:
        logger.warning(
            "Vehicle %s telemetry validation failed: %s | raw=%s",
            vehicle_id,
            exc.errors(),
            raw,
        )
        await websocket.send_json(
            {
                "type": "error",
                "vehicle_id": vehicle_id,
                "message": "Invalid vehicle telemetry",
                "detail": exc.errors(),
            }
        )
        return

    # --- 2. Store state --------------------------------------------------
    state = VehicleState(
        **telemetry.model_dump(),
        received_at=time.time(),
    )
    ws_manager.set_vehicle_state(vehicle_id, state)

    logger.info(
        "Vehicle %s telemetry OK: lat=%.6f lng=%.6f speed=%s heading=%s "
        "lane=%s lane_confidence=%s ts=%.3f",
        vehicle_id,
        state.lat,
        state.lng,
        state.speed_kmh,
        state.heading_deg,
        state.lane,
        state.lane_confidence,
        state.ts,
    )

    await websocket.send_json(
        {
            "type": "ack",
            "vehicle_id": vehicle_id,
            "message": "Vehicle telemetry accepted",
            "received_at": state.received_at,
        }
    )


@router.websocket("/ws/vehicle/{vehicle_id}")
async def vehicle_websocket(vehicle_id: str, websocket: WebSocket) -> None:
    """WebSocket endpoint for a participant vehicle."""
    ws_manager = get_ws_manager()

    await websocket.accept()
    ws_manager.add_vehicle(vehicle_id, websocket)
    logger.info("Vehicle %s connected", vehicle_id)

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            raw = message.get("text")
            if raw is None:
                await websocket.send_json(
                    {"type": "error", "vehicle_id": vehicle_id, "message": "Empty message"}
                )
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Vehicle %s sent non-JSON message: %s", vehicle_id, exc
                )
                await websocket.send_json(
                    {
                        "type": "error",
                        "vehicle_id": vehicle_id,
                        "message": "Message must be valid JSON",
                    }
                )
                continue

            if not isinstance(data, dict):
                await websocket.send_json(
                    {
                        "type": "error",
                        "vehicle_id": vehicle_id,
                        "message": "Message must be a JSON object",
                    }
                )
                continue

            await _handle_telemetry(vehicle_id, websocket, data)

    except WebSocketDisconnect:
        logger.info("Vehicle %s disconnected normally", vehicle_id)
    except Exception as exc:  # noqa: BLE001 - never crash the server
        logger.error(
            "Vehicle %s WebSocket error: %s", vehicle_id, exc, exc_info=True
        )
        try:
            await websocket.close(code=1011, reason="internal error")
        except Exception:  # noqa: BLE001
            pass
    finally:
        ws_manager.remove_vehicle(vehicle_id, websocket)
        logger.info("Vehicle %s cleaned up", vehicle_id)