"""
Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 1 — Backend Foundation + Real-Time Communication

main.py
=======
Assembles the FastAPI application from modular components.

This file should stay thin. Business logic lives in:
    - models.py            -> data models
    - websocket_manager.py -> connection + state management
    - route_engine.py      -> FUTURE route processing (STEP 2)
    - matching_engine.py   -> FUTURE vehicle matching (STEP 2)
    - api/                 -> HTTP + WebSocket routers
    - ai/                  -> FUTURE AI lane detection (STEP 3)

Where future steps connect:
    - STEP 2 (Route + Matching):
        * main.py instantiates route_engine.create_default_route_engine()
          and matching_engine.create_default_matching_engine().
        * The matching engine consumes AmbulanceState + VehicleState
          + Corridor (from route_engine) and returns MatchResult list.
        * api/vehicle.py and api/ambulance.py stay unchanged.
    - STEP 3 (AI Lane Detection + Alerts):
        * main.py instantiates ai.lane_model.load_model().
        * api/camera.py calls ai.lane_detection.detect_lane() and merges
          the result into VehicleState.
        * WebSocketManager.send_to_vehicle() is used to deliver the
          targeted emergency alert computed by the matching engine.

Run:
    pip install -r requirements.txt
    python -m uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Configuration (environment variables)
# ---------------------------------------------------------------------------
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("backend")

# ---------------------------------------------------------------------------
# Future-step singletons (STEP 2 / STEP 3 will replace these stubs)
# ---------------------------------------------------------------------------
# STEP 2: route_engine.create_default_route_engine() will return a real
# OSRM/graph engine. The matching engine consumes the route + corridor.
from route_engine import create_default_route_engine, RouteEngine
from matching_engine import create_default_matching_engine, MatchingEngine

route_engine: RouteEngine = create_default_route_engine()
matching_engine: MatchingEngine = create_default_matching_engine()

# STEP 3: ai.lane_model.load_model() will load the ML model. api/camera.py
# will call ai.lane_detection.detect_lane() to fill VehicleState.lane.
try:
    from ai.lane_model import load_model, LaneDetectionModel
    lane_model: LaneDetectionModel = load_model()
except Exception as exc:  # noqa: BLE001
    # The model is optional in Step 1. Do not crash the server.
    logger.warning("Lane model not loaded (expected in STEP 1): %s", exc)
    lane_model = None


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Backend starting on %s:%d", HOST, PORT)
    logger.info(
        "STEPS 1-8 active: route_engine=%s, matching_engine=%s, lane_model=%s",
        type(route_engine).__name__,
        type(matching_engine).__name__,
        type(lane_model).__name__,
    )
    yield
    # Shutdown: nothing to clean up here; WebSocket handlers use the
    # manager's finally blocks to clean their own connections.
    logger.info("Backend shutting down")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Lane-Aware Intelligent Emergency Vehicle Alert System",
    version="0.8.0 (STEPS 1-8)",
    description=(
        "Backend foundation for real-time ambulance + participant telemetry, "
        "spatial corridor matching, and camera-based lane/path estimation (STEPS 1-8)."
    ),
    lifespan=lifespan,
)

# CORS so the participant HTML frontend (served from another origin) can
# call the REST endpoints (e.g. GET /status) and upload camera frames.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from api.ambulance import router as ambulance_router
from api.vehicle import router as vehicle_router
from api.camera import router as camera_router

app.include_router(ambulance_router)
app.include_router(vehicle_router)
app.include_router(camera_router)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/status", tags=["status"])
async def status():
    """Return a snapshot of the current backend state.

    Does NOT expose sensitive information (no secrets, no credentials).
    """
    from websocket_manager import get_ws_manager
    import time

    ws = get_ws_manager()

    ambulance_state = None
    if ws.ambulance_state is not None:
        ambulance_state = ws.ambulance_state.model_dump()

    connected_vehicles = sorted(ws.connected_vehicles())
    vehicle_states = {
        vid: state.model_dump()
        for vid, state in ws.all_vehicle_states().items()
    }

    return {
        "status": "online",
        "version": app.version,
        "ambulance_connected": ws.ambulance_connected,
        "ambulance_state": ambulance_state,
        "connected_vehicles": connected_vehicles,
        "vehicle_states": vehicle_states,
        "vehicle_count": len(connected_vehicles),
        "timestamp": time.time(),
    }


@app.get("/health", tags=["status"])
async def health():
    """Simple liveness probe."""
    return {"status": "ok"}


@app.get("/", tags=["status"])
async def root():
    return {
        "service": "Lane-Aware Intelligent Emergency Vehicle Alert System",
        "step": "STEP 1 - Backend Foundation",
        "endpoints": {
            "ambulance_ws": "/ws/ambulance",
            "vehicle_ws": "/ws/vehicle/{vehicle_id}",
            "camera_frame": "/api/camera/frame/{vehicle_id}",
            "status": "/status",
            "health": "/health",
        },
    }