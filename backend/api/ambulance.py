"""
Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 1 — Backend Foundation + Real-Time Communication

api/ambulance.py
================
WebSocket endpoint for the ambulance (ESP32 + NEO-6M GPS).

Endpoint:
    WS /ws/ambulance

Flow (STEP 1):
    1. Ambulance connects -> registered in the WebSocket manager.
    2. Valid telemetry message arrives -> validated, stored as the
       current ambulance state, made available to /status.
    3. Invalid telemetry -> logged, error sent back to the client,
       server does NOT crash.
    4. Disconnect -> cleaned up from the manager.

Future steps connect here:
    - STEP 2: the route engine will consume AmbulanceState to compute
      the ambulance's planned route.
    - STEP 3: the matching engine will consume AmbulanceState together
      with vehicle states to decide who gets an alert.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from models import AmbulanceState, AmbulanceTelemetry
from websocket_manager import get_ws_manager

logger = logging.getLogger("backend.api.ambulance")

router = APIRouter(tags=["ambulance"])


def _serialize_state(state: AmbulanceState) -> Dict[str, Any]:
    """Convert an AmbulanceState to a plain JSON-serialisable dict."""
    return state.model_dump()


async def _handle_telemetry(websocket: WebSocket, raw: Any) -> None:
    """Validate an incoming telemetry message and update global state."""
    ws_manager = get_ws_manager()

    # --- 1. Validate -----------------------------------------------------
    try:
        telemetry = AmbulanceTelemetry.model_validate(raw)
    except ValidationError as exc:
        logger.warning(
            "Ambulance telemetry validation failed: %s | raw=%s",
            exc.errors(),
            raw,
        )
        await websocket.send_json(
            {
                "type": "error",
                "message": "Invalid ambulance telemetry",
                "detail": exc.errors(),
            }
        )
        return

    # --- 2. Store state --------------------------------------------------
    import time

    state = AmbulanceState(
        **telemetry.model_dump(),
        received_at=time.time(),
    )
    ws_manager.set_ambulance_state(state)

    logger.info(
        "Ambulance telemetry OK: lat=%.6f lng=%.6f speed=%.1f km/h "
        "heading=%.1f emergency=%s ts=%.3f",
        state.lat,
        state.lng,
        state.speed_kmh,
        state.heading_deg,
        state.emergency,
        state.ts,
    )

    # Acknowledge receipt so the ESP32 knows its data was accepted.
    await websocket.send_json(
        {
            "type": "ack",
            "message": "Ambulance telemetry accepted",
            "received_at": state.received_at,
        }
    )

    # Dispatch alerts and fleet updates
    try:
        from dispatch_service import dispatch_alerts_and_fleet
        await dispatch_alerts_and_fleet()
    except Exception as exc:  # noqa: BLE001
        logger.error("Error in dispatch_alerts_and_fleet: %s", exc, exc_info=True)


@router.websocket("/ws/ambulance")
async def ambulance_websocket(websocket: WebSocket) -> None:
    """WebSocket endpoint for the ambulance (ESP32)."""
    ws_manager = get_ws_manager()

    await websocket.accept()
    ws_manager.set_ambulance_connection(websocket)
    logger.info("Ambulance connected")

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            # The ESP32 sends JSON telemetry. We also tolerate plain text
            # frames containing a JSON object so the integration is robust.
            raw = message.get("text")
            if raw is None:
                await websocket.send_json(
                    {"type": "error", "message": "Empty message"}
                )
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.warning("Ambulance sent non-JSON message: %s", exc)
                await websocket.send_json(
                    {"type": "error", "message": "Message must be valid JSON"}
                )
                continue

            if not isinstance(data, dict):
                await websocket.send_json(
                    {"type": "error", "message": "Message must be a JSON object"}
                )
                continue

            await _handle_telemetry(websocket, data)

    except WebSocketDisconnect:
        logger.info("Ambulance disconnected normally")
    except Exception as exc:  # noqa: BLE001 - never crash the server
        logger.error("Ambulance WebSocket error: %s", exc, exc_info=True)
        try:
            await websocket.close(code=1011, reason="internal error")
        except Exception:  # noqa: BLE001
            pass
    finally:
        ws_manager.clear_ambulance_connection(websocket)
        logger.info("Ambulance connection cleaned up")