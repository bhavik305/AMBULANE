"""Full EVAS integration regression tests verifying OpenAPI schema, OpenStreetMap config,
route calculation, journey lifecycle, and device role transitions.
"""

import json
import pytest
from fastapi.testclient import TestClient

from main import app
from journey_service import get_journey_service
from websocket_manager import get_ws_manager


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_openapi_schema_generation(client):
    """PHASE 8: OpenAPI schema must generate without 500 internal server error."""
    response = client.get("/openapi.json")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    schema = response.json()
    assert "openapi" in schema
    assert "info" in schema
    assert "paths" in schema
    assert len(schema["paths"]) >= 20
    # Verify key endpoints are in schema
    assert "/openapi.json" in str(response.url)
    assert "/api/journey/start" in schema["paths"]
    assert "/api/journey/stop" in schema["paths"]
    assert "/api/journey/route" in schema["paths"]
    assert "/api/junction/config/{junction_id}" in schema["paths"]


def test_swagger_docs_accessible(client):
    """PHASE 8: Swagger /docs must return HTTP 200."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower() or "openapi" in response.text.lower()


def test_app_config_returns_openstreetmap_and_osrm(client):
    """PHASE 2: /api/config must specify OpenStreetMap and OSRM without requiring Google Maps API key."""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["map_provider"] == "openstreetmap"
    assert "tile.openstreetmap.org" in data["tile_url"]
    assert "OpenStreetMap" in data["attribution"]
    assert data["routing_service"] == "osrm"
    assert "lan_ip" in data
    assert "default_ws_url" in data


def test_journey_route_calculation_endpoint(client):
    """PHASE 4: Route calculation endpoint /api/journey/route."""
    # Test with Bangalore coordinates (MG Road to Brigade Road)
    params = {
        "origin_lat": 12.9716,
        "origin_lng": 77.5946,
        "dest_lat": 12.9740,
        "dest_lng": 77.5950,
    }
    response = client.get("/api/journey/route", params=params)
    assert response.status_code == 200
    data = response.json()
    assert "points" in data
    assert len(data["points"]) >= 2
    assert "distance_meters" in data
    assert data["distance_meters"] > 0
    assert "duration_seconds" in data
    assert data["status"] in ("ok", "fallback")


def test_journey_lifecycle_start_and_stop(client):
    """PHASES 3 & 4: Start and stop active ambulance journey."""
    start_payload = {
        "ambulance_id": "AMB01",
        "origin_name": "MG Road Station",
        "origin_lat": 12.9716,
        "origin_lng": 77.5946,
        "destination_name": "Bowring Hospital",
        "destination_lat": 12.9833,
        "destination_lng": 77.6053,
        "route_points": [
            {"lat": 12.9716, "lng": 77.5946},
            {"lat": 12.9770, "lng": 77.6000},
            {"lat": 12.9833, "lng": 77.6053},
        ],
        "distance_meters": 2400.0,
        "duration_seconds": 360.0,
        "assigned_lane": "CENTER",
        "admin_pin": "9911",
    }
    # 1. Start journey
    res_start = client.post("/api/journey/start", json=start_payload)
    assert res_start.status_code == 200
    j_data = res_start.json()
    assert j_data["ambulance_id"] == "AMB01"
    assert j_data["is_active"] is True
    assert j_data["assigned_lane"] == "CENTER"

    # 2. Check active journey query
    res_active = client.get("/api/journey/active")
    assert res_active.status_code == 200
    active_data = res_active.json()
    assert active_data["active"] is True
    assert active_data["journey"]["ambulance_id"] == "AMB01"

    # 3. Stop journey
    stop_payload = {
        "ambulance_id": "AMB01",
        "admin_pin": "9911",
    }
    res_stop = client.post("/api/journey/stop", json=stop_payload)
    assert res_stop.status_code == 200
    assert res_stop.json()["status"] == "stopped"

    # 4. Verify no active journey
    res_active_after = client.get("/api/journey/active")
    assert res_active_after.status_code == 200
    assert res_active_after.json()["active"] is False


def test_device_role_registration(client):
    """PHASES 3 & 5: Device registration for NORMAL_VEHICLE and AMBULANCE."""
    # Register normal vehicle
    veh_req = {
        "device_id": "V002",
        "role": "NORMAL_VEHICLE",
    }
    res_veh = client.post("/api/device/register", json=veh_req)
    assert res_veh.status_code == 200
    assert res_veh.json()["role"] == "NORMAL_VEHICLE"

    # Register ambulance with PIN
    amb_req = {
        "device_id": "AMB01",
        "role": "AMBULANCE",
        "admin_pin": "9911",
        "configured_lane": "RIGHT",
    }
    res_amb = client.post("/api/device/register", json=amb_req)
    assert res_amb.status_code == 200
    assert res_amb.json()["role"] == "AMBULANCE"
    assert res_amb.json()["configured_lane"] == "RIGHT"


def test_camera_status_and_lane_reporting(client):
    """PHASE 5: Camera status reports without crashing."""
    res = client.get("/api/camera/status")
    assert res.status_code == 200
    data = res.json()
    assert "camera_status" in data
    assert "camera_enabled" in data


def test_status_endpoint_empty_states(client):
    """PHASE 7: Status endpoint reports accurate online snapshot."""
    res = client.get("/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "vehicle_count" in data
    assert "connected_vehicles" in data


def test_frontend_static_assets_served(client):
    """PHASE 2 & 10: Leaflet and frontend static files are accessible."""
    res_index = client.get("/frontend/index.html")
    assert res_index.status_code == 200
    assert "Leaflet" in res_index.text or "leaflet" in res_index.text
    assert "OpenStreetMap" in res_index.text

    res_leaflet_js = client.get("/frontend/vendor/leaflet.js")
    assert res_leaflet_js.status_code == 200
    assert len(res_leaflet_js.content) > 10000

    res_leaflet_css = client.get("/frontend/vendor/leaflet.css")
    assert res_leaflet_css.status_code == 200
    assert len(res_leaflet_css.content) > 1000


def test_frontend_dom_ids_and_no_google_maps():
    """Verify all $(...) elements referenced in app.js exist in index.html and Google Maps is completely removed."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    index_html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    app_js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
    app_css = (root / "frontend" / "app.css").read_text(encoding="utf-8")

    # Verify no Google Maps API keys or gmaps elements
    assert "maps.googleapis.com" not in index_html
    assert "gmaps-setup-card" not in index_html
    assert "gmaps-setup-card" not in app_css

    # Check all $(...) in app.js exist in index.html
    js_ids = set(re.findall(r"\$\(['\"]([a-zA-Z0-9_-]+)['\"]\)", app_js))
    html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', index_html))
    missing = js_ids - html_ids
    assert not missing, f"Missing IDs referenced in app.js: {missing}"

