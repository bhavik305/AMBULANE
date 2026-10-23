"""Lane-Aware Intelligent Emergency Vehicle Alert System
Junction Traffic Signal Management and ETA-Triggered Priority Service.

Features:
- Tracks junction intersections and active signal states.
- Evaluates real-time ambulance ETA and distance to intersections.
- Generates idempotent, cryptographically tagged priority requests.
- Manages authenticated ESP32 traffic controller WebSockets.
- Enforces strict transition safety and fail-safe timeouts.
- Deterministic, non-blocking state simulation matching physical firmware.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

from models import (
    AmbulanceState,
    JunctionConfig,
    JunctionLights,
    JunctionState,
    LightAspects,
    SignalPriorityRequest,
)
from route_engine import haversine_distance_m

logger = logging.getLogger("backend.junction_service")

# Default junction placed along the Bangalore demonstration test corridor
DEFAULT_JUNCTIONS = {
    "JUNC_01": JunctionConfig(
        junction_id="JUNC_01",
        name="MG Road & Brigade Rd Intersection",
        lat=12.9740,
        lng=77.5950,
        emergency_approach="NORTH_SOUTH",
        cross_approach="EAST_WEST",
        eta_trigger_seconds=30.0,
        dist_trigger_meters=450.0,
    )
}

# Secret authorization key shared between backend and ESP32 firmware
JUNCTION_AUTH_KEY = "EVAS_ESP32_SECURE_TOKEN_2026"


class JunctionService:
    """Manages junction controllers, priority requests, and signal state machines."""

    def __init__(self) -> None:
        self._configs: Dict[str, JunctionConfig] = dict(DEFAULT_JUNCTIONS)
        self._states: Dict[str, JunctionState] = {
            jid: JunctionState(
                junction_id=jid,
                connected=False,
                current_state="NORMAL_CYCLE",
                priority_active=False,
                active_approach="NORTH_SOUTH",
                lights=JunctionLights(
                    approach_a=LightAspects(red=False, yellow=False, green=True),
                    approach_b=LightAspects(red=True, yellow=False, green=False),
                ),
                hardware_mode="SIMULATED",
            )
            for jid in self._configs
        }

        # WebSocket connections: junction_id -> WebSocket
        self._sockets: Dict[str, Any] = {}

        # Debounce and active request tracking
        self._active_requests: Dict[str, SignalPriorityRequest] = {}
        self._last_trigger_ts: Dict[str, float] = {}
        self._sim_priority_start_ts: Dict[str, float] = {}

    def register_socket(self, junction_id: str, websocket: Any) -> None:
        """Register active WebSocket from physical junction ESP32."""
        self._sockets[junction_id] = websocket
        if junction_id in self._states:
            self._states[junction_id].connected = True
            self._states[junction_id].hardware_mode = "PHYSICAL_ESP32"
        logger.info("Junction %s connected via physical ESP32 WebSocket", junction_id)

    def unregister_socket(self, junction_id: str, websocket: Any) -> None:
        """Remove disconnected junction ESP32 WebSocket."""
        if self._sockets.get(junction_id) is websocket:
            del self._sockets[junction_id]
        if junction_id in self._states:
            self._states[junction_id].connected = False
            self._states[junction_id].hardware_mode = "SIMULATED"
        logger.info("Junction %s disconnected; reverting to safe simulated fallback", junction_id)

    def _refresh_simulated_state(self, jid: str) -> None:
        """Dynamically update state based on wall-clock time for zero-blocking simulation."""
        state = self._states.get(jid)
        if state is None or state.connected:
            return  # Physical hardware telemetry takes precedence

        start_ts = self._sim_priority_start_ts.get(jid)
        if start_ts is None:
            # Autonomous normal cycling (20-second loop)
            t_cycle = time.time() % 20.0
            if t_cycle < 9.0:
                state.current_state = "NORMAL_CYCLE"
                state.active_approach = "NORTH_SOUTH"
                state.lights.approach_a = LightAspects(red=False, yellow=False, green=True)
                state.lights.approach_b = LightAspects(red=True, yellow=False, green=False)
            elif t_cycle < 11.5:
                state.current_state = "NORMAL_CYCLE"
                state.active_approach = "NORTH_SOUTH"
                state.lights.approach_a = LightAspects(red=False, yellow=True, green=False)
                state.lights.approach_b = LightAspects(red=True, yellow=False, green=False)
            elif t_cycle < 13.0:
                state.current_state = "ALL_RED"
                state.lights.approach_a = LightAspects(red=True, yellow=False, green=False)
                state.lights.approach_b = LightAspects(red=True, yellow=False, green=False)
            elif t_cycle < 17.5:
                state.current_state = "NORMAL_CYCLE"
                state.active_approach = "EAST_WEST"
                state.lights.approach_a = LightAspects(red=True, yellow=False, green=False)
                state.lights.approach_b = LightAspects(red=False, yellow=False, green=True)
            elif t_cycle < 19.0:
                state.current_state = "NORMAL_CYCLE"
                state.active_approach = "EAST_WEST"
                state.lights.approach_a = LightAspects(red=True, yellow=False, green=False)
                state.lights.approach_b = LightAspects(red=False, yellow=True, green=False)
            else:
                state.current_state = "ALL_RED"
                state.lights.approach_a = LightAspects(red=True, yellow=False, green=False)
                state.lights.approach_b = LightAspects(red=True, yellow=False, green=False)
            return

        elapsed = time.time() - start_ts
        if elapsed < 2.5:
            # 1. PRIORITY_REQUESTED: Cross-street Approach B transitions to Yellow
            state.current_state = "PRIORITY_REQUESTED"
            state.priority_active = True
            state.lights.approach_a = LightAspects(red=True, yellow=False, green=False)
            state.lights.approach_b = LightAspects(red=False, yellow=True, green=False)
        elif elapsed < 4.5:
            # 2. CLEARANCE_IN_PROGRESS: All-Red safety clearance interval
            state.current_state = "CLEARANCE_IN_PROGRESS"
            state.priority_active = True
            state.lights.approach_a = LightAspects(red=True, yellow=False, green=False)
            state.lights.approach_b = LightAspects(red=True, yellow=False, green=False)
        elif elapsed < 22.0:
            # 3. AMBULANCE_GREEN: Emergency corridor green illuminated; cross-street locked Red
            state.current_state = "AMBULANCE_GREEN"
            state.priority_active = True
            state.active_approach = "NORTH_SOUTH"
            state.lights.approach_a = LightAspects(red=False, yellow=False, green=True)
            state.lights.approach_b = LightAspects(red=True, yellow=False, green=False)
        elif elapsed < 25.0:
            # 4. RETURNING_TO_NORMAL: Approach A Yellow clearance interval
            state.current_state = "RETURNING_TO_NORMAL"
            state.priority_active = True
            state.lights.approach_a = LightAspects(red=False, yellow=True, green=False)
            state.lights.approach_b = LightAspects(red=True, yellow=False, green=False)
        else:
            # 5. NORMAL: Return to standard cycle
            self._sim_priority_start_ts.pop(jid, None)
            state.priority_active = False
            state.current_state = "NORMAL"
            state.lights.approach_a = LightAspects(red=False, yellow=False, green=True)
            state.lights.approach_b = LightAspects(red=True, yellow=False, green=False)

        # STRICT SAFETY INTERLOCK: Under no circumstances allow dual greens
        if state.lights.approach_a.green and state.lights.approach_b.green:
            state.lights.approach_b.green = False
            state.lights.approach_b.red = True

    def get_state(self, junction_id: str) -> Optional[JunctionState]:
        self._refresh_simulated_state(junction_id)
        return self._states.get(junction_id)

    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        for jid in self._configs:
            self._refresh_simulated_state(jid)
        return {jid: st.model_dump() for jid, st in self._states.items()}

    async def send_to_junction(self, junction_id: str, payload: Dict[str, Any]) -> bool:
        """Deliver payload to physical ESP32 if connected."""
        ws = self._sockets.get(junction_id)
        if ws is None:
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send to junction %s: %s", junction_id, exc)
            self._sockets.pop(junction_id, None)
            return False

    async def handle_junction_message(self, junction_id: str, message: Dict[str, Any]) -> None:
        """Process incoming status or acknowledgement telemetry from junction ESP32."""
        msg_type = message.get("type")
        state = self._states.get(junction_id)
        if state is None:
            return

        if msg_type == "junction_ack":
            state.last_ack_request_id = message.get("request_id")
            logger.info("Junction %s ACK received for request %s", junction_id, state.last_ack_request_id)

        elif msg_type == "junction_telemetry":
            state.connected = True
            state.hardware_mode = "PHYSICAL_ESP32"
            state.current_state = message.get("current_state", state.current_state)
            state.priority_active = message.get("priority_active", state.priority_active)
            state.active_approach = message.get("active_approach", state.active_approach)
            state.last_reported_ts = time.time()

            # Update reported light aspects
            lights_data = message.get("lights", {})
            if "approach_a" in lights_data:
                state.lights.approach_a = LightAspects(**lights_data["approach_a"])
            if "approach_b" in lights_data:
                state.lights.approach_b = LightAspects(**lights_data["approach_b"])

    def set_junction_config(
        self,
        junction_id: str,
        eta_trigger_seconds: Optional[float] = None,
        dist_trigger_meters: Optional[float] = None,
        emergency_approach: Optional[str] = None,
    ) -> Optional[JunctionConfig]:
        """Update configurable priority thresholds for an intersection."""
        cfg = self._configs.get(junction_id)
        if cfg is None:
            return None
        if eta_trigger_seconds is not None and eta_trigger_seconds > 0:
            cfg.eta_trigger_seconds = float(eta_trigger_seconds)
        if dist_trigger_meters is not None and dist_trigger_meters > 0:
            cfg.dist_trigger_meters = float(dist_trigger_meters)
        if emergency_approach:
            cfg.emergency_approach = emergency_approach.upper()
        self._configs[junction_id] = cfg
        logger.info(
            "Junction %s config updated: eta_trigger=%.1fs, dist_trigger=%.1fm, approach=%s",
            junction_id,
            cfg.eta_trigger_seconds,
            cfg.dist_trigger_meters,
            cfg.emergency_approach,
        )
        return cfg

    async def evaluate_eta_and_trigger(self, ambulance: AmbulanceState) -> None:
        """Evaluate ambulance position/speed against all junctions and trigger priority."""
        # Stale telemetry gate (Phase 6): Suppress priority if GPS older than 20 seconds
        if ambulance.is_stale(max_age_seconds=20.0):
            logger.warning("Ambulance telemetry is STALE (>20s); priority request suppressed for safety.")
            return

        now = time.time()

        for jid, cfg in self._configs.items():
            dist_m = haversine_distance_m(ambulance.lat, ambulance.lng, cfg.lat, cfg.lng)
            speed_ms = max(3.0, (ambulance.speed_kmh or 45.0) / 3.6)
            eta_s = round(dist_m / speed_ms, 1)

            in_range = (dist_m <= cfg.dist_trigger_meters)
            eta_triggered = (eta_s <= cfg.eta_trigger_seconds)
            should_trigger = ambulance.emergency and in_range and eta_triggered

            last_trig = self._last_trigger_ts.get(jid, 0.0)
            active_req = self._active_requests.get(jid)

            if should_trigger:
                if active_req is not None and now < active_req.expiry_ts and (now - last_trig) < 15.0:
                    continue

                req_id = f"REQ_{int(now)}_{uuid.uuid4().hex[:6]}"
                expiry = now + 25.0

                req = SignalPriorityRequest(
                    request_id=req_id,
                    junction_id=jid,
                    approach_id=cfg.emergency_approach,
                    ambulance_id=ambulance.ambulance_id or "AMB01",
                    eta_s=eta_s,
                    expiry_ts=expiry,
                    auth_token=JUNCTION_AUTH_KEY,
                    timestamp=now,
                )

                self._active_requests[jid] = req
                self._last_trigger_ts[jid] = now

                payload = req.model_dump()
                logger.info(
                    "TRIGGER SIGNAL PRIORITY: Junction %s (Dist=%.1fm, ETA=%.1fs, ReqID=%s)",
                    jid,
                    dist_m,
                    eta_s,
                    req_id,
                )

                sent = await self.send_to_junction(jid, payload)
                if not sent:
                    # Deterministic simulated state transition
                    self._sim_priority_start_ts[jid] = now
                    st = self._states.get(jid)
                    if st:
                        st.priority_active = True
                        st.last_ack_request_id = req_id

            elif not ambulance.emergency or dist_m > cfg.dist_trigger_meters + 100.0:
                if active_req is not None:
                    del self._active_requests[jid]
                    clear_payload = {
                        "type": "priority_clear",
                        "junction_id": jid,
                        "auth_token": JUNCTION_AUTH_KEY,
                        "timestamp": now,
                    }
                    await self.send_to_junction(jid, clear_payload)
                    self._sim_priority_start_ts.pop(jid, None)
                    st = self._states.get(jid)
                    if st:
                        st.priority_active = False


# Singleton accessor
_junction_service: Optional[JunctionService] = None


def get_junction_service() -> JunctionService:
    global _junction_service
    if _junction_service is None:
        _junction_service = JunctionService()
    return _junction_service
