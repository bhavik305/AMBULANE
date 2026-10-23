"""Lane-Aware Intelligent Emergency Vehicle Alert System
PHASE 8: Honest Demonstration Mode REST Endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from fastapi import APIRouter, Request
from demo_fixtures import load_deterministic_scenario

logger = logging.getLogger("backend.api.demo")

router = APIRouter(tags=["demo"])


@router.post("/api/demo/scenario")
async def trigger_demo_scenario(request: Request, scenario_id: str = "DIRECT_BLOCKING") -> Dict[str, Any]:
    """Execute a documented, deterministic demonstration scenario without fabricated telemetry."""
    target_id = scenario_id
    try:
        body = await request.json()
        if isinstance(body, dict) and "scenario_id" in body and body["scenario_id"]:
            target_id = body["scenario_id"]
    except Exception:
        pass
    return await load_deterministic_scenario(target_id)


@router.get("/api/demo/scenarios")
async def list_demo_scenarios():
    """List available documented demonstration scenarios with expected results."""
    return {
        "data_mode": "TEST_DATA_SIMULATED",
        "scenarios": [
            {
                "id": "DIRECT_BLOCKING",
                "title": "Scenario 1: Direct Same-Lane Conflict",
                "description": "Ambulance in designated CENTER lane; Vehicle V001 ahead in CENTER lane at 178m.",
                "expected": "Direct Conflict (DIRECT_BLOCKING) -> EVACUATE LANE alert.",
            },
            {
                "id": "ADJACENT_CLEAR",
                "title": "Scenario 2: Adjacent Lane Clearance",
                "description": "Ambulance in designated CENTER lane; Vehicle V001 ahead in LEFT lane at 150m.",
                "expected": "Adjacent Lane (ADJACENT_CLEAR) -> Maintain Course advisory.",
            },
            {
                "id": "UNKNOWN_LANE",
                "title": "Scenario 3: Ambiguous / Occluded Camera Lane",
                "description": "Vehicle lane camera markings occluded (UNKNOWN lane).",
                "expected": "Caution advisory (UNKNOWN_CAUTION) -> Stay alert.",
            },
            {
                "id": "ETA_SIGNAL_PREEMPTION",
                "title": "Scenario 4: ETA-Triggered Traffic Signal Preemption",
                "description": "Ambulance within 30s ETA of JUNC_01 intersection.",
                "expected": "Priority request sent to junction ESP32 -> Approach B Yellow -> All-Red -> Green corridor.",
            },
            {
                "id": "STALE_TELEMETRY",
                "title": "Scenario 5: Stale Telemetry Safety Suppression",
                "description": "Ambulance GPS older than 20 seconds.",
                "expected": "Signal priority suppressed for safety; active alerts cleared.",
            },
        ],
    }
