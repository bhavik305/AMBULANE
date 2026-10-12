"""
Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 1 — Backend Foundation + Real-Time Communication

websocket_manager.py
====================
Central manager for all WebSocket connections and the shared runtime
state (ambulance state + connected vehicle states).

Responsibilities:
    - Track the single ambulance WebSocket connection.
    - Track multiple participant vehicle WebSocket connections.
    - Store the latest validated state for the ambulance and each vehicle.
    - Provide a clean send_to_vehicle(vehicle_id, message) helper that
      STEP 3 will use to deliver targeted emergency alerts.
    - Provide a broadcast() helper for future use (e.g. status pushes).

The manager is a module-level singleton accessed via get_ws_manager().
This keeps the WebSocket handlers in api/ thin and testable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set

from models import AmbulanceState, VehicleState

logger = logging.getLogger("backend.websocket_manager")


class WebSocketManager:
    """Thread-safe (asyncio-safe) manager for WebSocket connections."""

    def __init__(self) -> None:
        # The ambulance is a single connection.
        self._ambulance_ws: Optional[Any] = None
        self._ambulance_state: Optional[AmbulanceState] = None

        # Participant vehicles: vehicle_id -> WebSocket.
        self._vehicles: Dict[str, Any] = {}
        # Latest validated state per vehicle.
        self._vehicle_states: Dict[str, VehicleState] = {}

    # ------------------------------------------------------------------
    # Ambulance connection management
    # ------------------------------------------------------------------
    def set_ambulance_connection(self, websocket: Any) -> None:
        """Register the ambulance WebSocket connection."""
        self._ambulance_ws = websocket
        logger.info("Ambulance WebSocket registered")

    def clear_ambulance_connection(self, websocket: Any) -> None:
        """Remove the ambulance WebSocket connection (only if it matches)."""
        if self._ambulance_ws is websocket:
            self._ambulance_ws = None
        logger.info("Ambulance WebSocket cleared")

    def set_ambulance_state(self, state: AmbulanceState) -> None:
        """Store the latest validated ambulance state."""
        self._ambulance_state = state

    @property
    def ambulance_state(self) -> Optional[AmbulanceState]:
        return self._ambulance_state

    @property
    def ambulance_connected(self) -> bool:
        return self._ambulance_ws is not None

    # ------------------------------------------------------------------
    # Vehicle connection management
    # ------------------------------------------------------------------
    def add_vehicle(self, vehicle_id: str, websocket: Any) -> None:
        """Register a participant vehicle connection."""
        self._vehicles[vehicle_id] = websocket
        logger.info("Vehicle %s registered (total=%d)", vehicle_id, len(self._vehicles))

    def remove_vehicle(self, vehicle_id: str, websocket: Any) -> None:
        """Remove a participant vehicle connection (only if it matches)."""
        if self._vehicles.get(vehicle_id) is websocket:
            del self._vehicles[vehicle_id]
        self._vehicle_states.pop(vehicle_id, None)
        logger.info("Vehicle %s removed (total=%d)", vehicle_id, len(self._vehicles))

    def has_vehicle(self, vehicle_id: str) -> bool:
        """Return True if the vehicle is currently connected."""
        return vehicle_id in self._vehicles

    def set_vehicle_state(self, vehicle_id: str, state: VehicleState) -> None:
        """Store the latest validated state for a vehicle."""
        self._vehicle_states[vehicle_id] = state

    def get_vehicle_state(self, vehicle_id: str) -> Optional[VehicleState]:
        return self._vehicle_states.get(vehicle_id)

    def connected_vehicles(self) -> Set[str]:
        """Return the set of currently connected vehicle IDs."""
        return set(self._vehicles.keys())

    def all_vehicle_states(self) -> Dict[str, VehicleState]:
        """Return a snapshot copy of all vehicle states."""
        return dict(self._vehicle_states)

    def get_fresh_ambulance_state(self, max_age_seconds: float = 30.0) -> Optional[AmbulanceState]:
        """Return the ambulance state if not stale, else None."""
        if self._ambulance_state is None:
            return None
        if self._ambulance_state.is_stale(max_age_seconds=max_age_seconds):
            logger.warning("Ambulance telemetry is stale (>%.1fs old)", max_age_seconds)
            return None
        return self._ambulance_state

    def get_fresh_vehicle_states(self, max_age_seconds: float = 30.0) -> Dict[str, VehicleState]:
        """Return fresh states belonging to currently connected vehicles only."""
        fresh = {}
        for vid in self.connected_vehicles():
            state = self._vehicle_states.get(vid)
            if state is not None and not state.is_stale(max_age_seconds=max_age_seconds):
                fresh[vid] = state
        return fresh

    # ------------------------------------------------------------------
    # Messaging helpers
    # ------------------------------------------------------------------
    async def send_to_vehicle(self, vehicle_id: str, message: Any) -> bool:
        """Send a message to a single vehicle by id.

        Returns True if the message was sent, False if the vehicle is
        not connected.

        STEP 3 will use this to deliver targeted emergency alerts.
        """
        websocket = self._vehicles.get(vehicle_id)
        if websocket is None:
            logger.debug("send_to_vehicle: vehicle %s not connected", vehicle_id)
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("send_to_vehicle %s failed: %s", vehicle_id, exc, exc_info=True)
            # Remove a dead connection so it does not linger.
            self._vehicles.pop(vehicle_id, None)
            self._vehicle_states.pop(vehicle_id, None)
            return False

    async def send_to_ambulance(self, message: Any) -> bool:
        """Send a message to the ambulance (if connected)."""
        if self._ambulance_ws is None:
            return False
        try:
            await self._ambulance_ws.send_json(message)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("send_to_ambulance failed: %s", exc, exc_info=True)
            return False

    async def broadcast(self, message: Any, exclude: Optional[str] = None) -> int:
        """Send a message to every connected vehicle (optionally excluding one).

        Returns the number of successful deliveries. Reserved for
        future use (e.g. broadcast alerts or status pushes).
        """
        sent = 0
        for vehicle_id, websocket in list(self._vehicles.items()):
            if exclude is not None and vehicle_id == exclude:
                continue
            try:
                await websocket.send_json(message)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("broadcast to %s failed: %s", vehicle_id, exc, exc_info=True)
                self._vehicles.pop(vehicle_id, None)
                self._vehicle_states.pop(vehicle_id, None)
        return sent


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_manager: Optional[WebSocketManager] = None


def get_ws_manager() -> WebSocketManager:
    """Return the process-wide WebSocketManager singleton.

    Using a function (rather than a module-level global) makes the
    manager easy to swap in tests by patching get_ws_manager.
    """
    global _manager
    if _manager is None:
        _manager = WebSocketManager()
    return _manager


def reset_ws_manager() -> None:
    """Reset the singleton. Useful for tests."""
    global _manager
    _manager = None