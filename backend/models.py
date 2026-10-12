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

from __future__ import annotations

import time
from typing import Optional

from pydantic import BaseModel, Field


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