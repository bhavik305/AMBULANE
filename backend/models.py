"""
Lane-Aware Intelligent Emergency Vehicle Alert System
STEP 1 — Backend Foundation + Real-Time Communication

models.py
---------
Central Pydantic data models used across the backend.

These models are intentionally designed so that future steps
can reuse them without breaking backward compatibility:

- STEP 2 (Route Processing + Vehicle Matching Intelligence)
  will consume AmbulanceState / VehicleState to compute routes
  and match vehicles to the ambulance corridor.

- STEP 3 (AI/ML Lane Detection + Final Alert Integration)
  will add lane / lane_confidence fields to VehicleState and
  feed them into the matching engine.
"""

from enum import Enum
import time
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Device Registration & Roles (PHASE 4)
# ---------------------------------------------------------------------------
class DeviceRole(str, Enum):
    AMBULANCE = "AMBULANCE"
    NORMAL_VEHICLE = "NORMAL_VEHICLE"


class DeviceRegistration(BaseModel):
    device_id: str = Field(..., min_length=1, description="Unique alphanumeric device identifier")
    role: DeviceRole = Field(..., description="Role of the registered device")
    auth_token: str = Field(..., description="Token issued upon successful registration")
    registered_at: float = Field(..., description="Unix timestamp of registration")
    configured_lane: Optional[str] = Field(default="CENTER", description="Fixed designated road lane")
    configured_approach: Optional[str] = Field(default="NORTH_SOUTH", description="Fixed approach corridor")
    road_corridor_id: Optional[str] = Field(default="CORRIDOR_MG_ROAD", description="Designated road corridor")


class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(..., min_length=1, description="Unique device ID to register")
    role: DeviceRole = Field(default=DeviceRole.NORMAL_VEHICLE, description="Device role: AMBULANCE or NORMAL_VEHICLE")
    admin_pin: Optional[str] = Field(default=None, description="Required authorization PIN when registering as AMBULANCE")
    configured_lane: Optional[str] = Field(default="CENTER", description="Fixed designated lane for ambulance")
    configured_approach: Optional[str] = Field(default="NORTH_SOUTH", description="Designated approach at intersections")


class AmbulanceConfigRequest(BaseModel):
    ambulance_id: str = Field(default="AMB01", description="Identifier of the emergency vehicle")
    configured_lane: Optional[str] = Field(default=None, description="Fixed designated ambulance lane, e.g. LEFT, CENTER, RIGHT")
    designated_lane: Optional[str] = Field(default=None, description="Alias for configured_lane")
    configured_approach: str = Field(default="NORTH_SOUTH", description="Fixed intended intersection approach")
    designated_approach: Optional[str] = Field(default=None, description="Alias for configured_approach")
    auth_token: Optional[str] = Field(default=None, description="Authorization token from ambulance registration")

    def model_post_init(self, __context: Any) -> None:
        if self.configured_lane is None:
            self.configured_lane = self.designated_lane or "CENTER"
        if self.designated_approach is not None:
            self.configured_approach = self.designated_approach


# ---------------------------------------------------------------------------
# Ambulance telemetry
# ---------------------------------------------------------------------------
# The ESP32 + NEO-6M GPS module sends this shape over WS /ws/ambulance:
#
#   {
#       "lat": number,
#       "lng": number,
#       "speed_kmh": number,
#       "heading_deg": number,
#       "emergency": boolean,
#       "ts": number
#   }
#
# `ambulance_id` is optional today and reserved for future multi-ambulance
# deployments. It must NOT break the current ESP32 firmware.
# ---------------------------------------------------------------------------
class AmbulanceTelemetry(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees (-90..90)")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees (-180..180)")
    speed_kmh: float = Field(..., ge=0.0, description="Speed in kilometres per hour")
    heading_deg: float = Field(
        ..., ge=0.0, lt=360.0, description="Heading in degrees (0=N, 90=E, ...)"
    )
    emergency: bool = Field(..., description="Whether the ambulance is in emergency mode")
    ts: float = Field(..., gt=0.0, description="Unix timestamp (seconds) of the reading")

    # Reserved for future multi-ambulance deployments.
    # The current ESP32 firmware does NOT send this field, so it must be
    # optional to preserve backward compatibility.
    ambulance_id: Optional[str] = Field(
        default=None,
        description="Optional ambulance identifier (future multi-ambulance support)",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_ambulance_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize latitude / longitude
            if "latitude" in data and "lat" not in data:
                data["lat"] = data["latitude"]
            if "longitude" in data and "lng" not in data:
                data["lng"] = data["longitude"]
            if "speed" in data and "speed_kmh" not in data:
                data["speed_kmh"] = data["speed"]
            if "heading" in data and "heading_deg" not in data:
                data["heading_deg"] = data["heading"]
            if "id" in data and "ambulance_id" not in data:
                data["ambulance_id"] = data["id"]
            if "timestamp" in data and "ts" not in data:
                ts_val = data["timestamp"]
                if isinstance(ts_val, (int, float)):
                    data["ts"] = float(ts_val)
                elif isinstance(ts_val, str):
                    try:
                        from datetime import datetime
                        data["ts"] = datetime.fromisoformat(ts_val.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        data["ts"] = time.time()
        return data


class AmbulanceState(AmbulanceTelemetry):
    """The latest validated ambulance state held by the backend."""

    # When the backend stores the state it may stamp its own received-at
    # timestamp so the /status endpoint can report data freshness.
    received_at: Optional[float] = Field(
        default=None, description="Backend-side Unix timestamp when state was stored"
    )

    def is_stale(self, max_age_seconds: float = 30.0, current_time: Optional[float] = None) -> bool:
        """Return True if state age exceeds max_age_seconds."""
        now = current_time if current_time is not None else time.time()
        effective_ts = self.received_at if self.received_at is not None else self.ts
        return (now - effective_ts) > max_age_seconds


# ---------------------------------------------------------------------------
# Participant vehicle telemetry
# ---------------------------------------------------------------------------
# The participant phone app connects via WS /ws/vehicle/{vehicle_id} and
# sends telemetry. Today the phone may ONLY send lat/lng. The model below
# therefore makes speed_kmh, heading_deg, lane and lane_confidence OPTIONAL
# so the current minimal client keeps working while richer clients (and
# future STEP 3 AI lane detection) can supply extra fields later.
#
# We NEVER fabricate lane values. If a field is missing it stays None.
# ---------------------------------------------------------------------------
class VehicleTelemetry(BaseModel):
    vehicle_id: str = Field(..., min_length=1, description="Unique vehicle identifier")

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees (-90..90)")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees (-180..180)")

    # These fields are OPTIONAL today. A phone that only reports GPS
    # position will omit them. STEP 3 will populate them from the camera
    # + AI lane-detection pipeline.
    speed_kmh: Optional[float] = Field(
        default=None, ge=0.0, description="Speed in kilometres per hour"
    )
    heading_deg: Optional[float] = Field(
        default=None, ge=0.0, lt=360.0, description="Heading in degrees (0=N, 90=E, ...)"
    )
    lane: Optional[str] = Field(
        default=None,
        description="Lane label, e.g. 'LEFT', 'CENTER', 'RIGHT' (STEP 3 fills this)",
    )
    lane_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score 0..1 for the lane label (STEP 3 fills this)",
    )

    ts: float = Field(..., gt=0.0, description="Unix timestamp (seconds) of the reading")

    @model_validator(mode="before")
    @classmethod
    def _normalize_vehicle_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize aliases
            if "latitude" in data and "lat" not in data:
                data["lat"] = data["latitude"]
            if "longitude" in data and "lng" not in data:
                data["lng"] = data["longitude"]
            if "speed" in data and "speed_kmh" not in data:
                data["speed_kmh"] = data["speed"]
            if "heading" in data and "heading_deg" not in data:
                data["heading_deg"] = data["heading"]
            if "id" in data and "vehicle_id" not in data:
                data["vehicle_id"] = data["id"]
            if "timestamp" in data and "ts" not in data:
                ts_val = data["timestamp"]
                if isinstance(ts_val, (int, float)):
                    data["ts"] = float(ts_val)
                elif isinstance(ts_val, str):
                    try:
                        from datetime import datetime
                        data["ts"] = datetime.fromisoformat(ts_val.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        data["ts"] = time.time()
            if "lane" in data and data["lane"] is not None:
                data["lane"] = str(data["lane"])
        return data


class VehicleState(VehicleTelemetry):
    """The latest validated vehicle state held by the backend."""

    received_at: Optional[float] = Field(
        default=None, description="Backend-side Unix timestamp when state was stored"
    )

    def is_stale(self, max_age_seconds: float = 30.0, current_time: Optional[float] = None) -> bool:
        """Return True if state age exceeds max_age_seconds."""
        now = current_time if current_time is not None else time.time()
        effective_ts = self.received_at if self.received_at is not None else self.ts
        return (now - effective_ts) > max_age_seconds


# ---------------------------------------------------------------------------
# Junction & Traffic Signal Priority Models
# ---------------------------------------------------------------------------
class JunctionConfig(BaseModel):
    junction_id: str = Field(..., description="Unique junction identifier, e.g. JUNC_01")
    name: str = Field(..., description="Human-readable name of the intersection")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Intersection latitude")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Intersection longitude")
    emergency_approach: str = Field(default="NORTH_SOUTH", description="Approach ID cleared for emergency vehicle")
    cross_approach: str = Field(default="EAST_WEST", description="Cross-traffic approach ID")
    eta_trigger_seconds: float = Field(default=30.0, description="ETA in seconds when priority is requested")
    dist_trigger_meters: float = Field(default=450.0, description="Max distance in meters to trigger priority")


class SignalPriorityRequest(BaseModel):
    type: str = "priority_request"
    request_id: str = Field(..., description="Unique idempotency ID for request")
    junction_id: str
    approach_id: str
    ambulance_id: str
    eta_s: float
    expiry_ts: float
    auth_token: str
    timestamp: float


class LightAspects(BaseModel):
    red: bool = False
    yellow: bool = False
    green: bool = False


class JunctionLights(BaseModel):
    approach_a: LightAspects = Field(default_factory=LightAspects)
    approach_b: LightAspects = Field(default_factory=LightAspects)


class JunctionState(BaseModel):
    junction_id: str
    connected: bool = False
    current_state: str = "NORMAL_CYCLE"  # NORMAL_CYCLE, PRIORITY_TRANSITION, PRIORITY_HOLD, ALL_RED
    priority_active: bool = False
    active_approach: str = "NORTH_SOUTH"
    lights: JunctionLights = Field(default_factory=JunctionLights)
    last_ack_request_id: Optional[str] = None
    last_reported_ts: float = 0.0
    hardware_mode: str = "SIMULATED"  # PHYSICAL_ESP32 or SIMULATED


# ---------------------------------------------------------------------------
# Active Ambulance Journey Models (PHASES 3 & 4)
# ---------------------------------------------------------------------------
class ActiveJourney(BaseModel):
    journey_id: str = Field(..., description="Unique journey identifier")
    ambulance_id: str = Field(default="AMB01", description="Identifier of the emergency vehicle")
    origin_name: Optional[str] = Field(default=None, description="Human-readable origin address/name")
    origin_lat: float = Field(..., ge=-90.0, le=90.0, description="Origin latitude")
    origin_lng: float = Field(..., ge=-180.0, le=180.0, description="Origin longitude")
    destination_name: Optional[str] = Field(default=None, description="Human-readable destination address/name")
    destination_lat: float = Field(..., ge=-90.0, le=90.0, description="Destination latitude")
    destination_lng: float = Field(..., ge=-180.0, le=180.0, description="Destination longitude")
    route_points: list[dict[str, float]] = Field(
        default_factory=list,
        description="List of road-following coordinates: [{'lat': float, 'lng': float}]",
    )
    distance_meters: float = Field(default=0.0, ge=0.0, description="Total route distance in meters")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Estimated duration in seconds")
    assigned_lane: str = Field(default="CENTER", description="Configured ambulance lane: LEFT, CENTER, RIGHT")
    is_active: bool = Field(default=True, description="Whether journey is actively underway")
    started_at: float = Field(..., description="Unix timestamp when journey started")
    stopped_at: Optional[float] = Field(default=None, description="Unix timestamp when journey finished")


class StartJourneyRequest(BaseModel):
    ambulance_id: str = Field(default="AMB01", description="Identifier of the emergency vehicle")
    origin_name: Optional[str] = Field(default=None, description="Human-readable origin name")
    origin_lat: float = Field(..., ge=-90.0, le=90.0, description="Origin latitude")
    origin_lng: float = Field(..., ge=-180.0, le=180.0, description="Origin longitude")
    destination_name: Optional[str] = Field(default=None, description="Human-readable destination name")
    destination_lat: float = Field(..., ge=-90.0, le=90.0, description="Destination latitude")
    destination_lng: float = Field(..., ge=-180.0, le=180.0, description="Destination longitude")
    route_points: list[dict[str, float]] = Field(
        default_factory=list,
        description="Road-following route points [{'lat': float, 'lng': float}]",
    )
    distance_meters: float = Field(default=0.0, ge=0.0, description="Route distance in meters")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Route duration in seconds")
    assigned_lane: str = Field(default="CENTER", description="Configured ambulance clearance lane")
    admin_pin: Optional[str] = Field(default=None, description="Admin authorization PIN if required")


class StopJourneyRequest(BaseModel):
    ambulance_id: str = Field(default="AMB01", description="Identifier of the emergency vehicle")
    admin_pin: Optional[str] = Field(default=None, description="Admin authorization PIN if required")