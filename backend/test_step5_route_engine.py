"""Step 5 Route Engine Unit and Mock Tests."""

import json
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from route_engine import (
    OSRMRouteEngine,
    Route,
    RouteEngine,
    RoutePoint,
    RoutingError,
)


def test_corridor_geometry_and_membership():
    engine = RouteEngine()

    # Route along a straight line in Bangalore
    # (12.9716, 77.5946) to (12.9816, 77.5946) -> North ~ 1.11 km
    p1 = RoutePoint(lat=12.9716, lng=77.5946)
    p2 = RoutePoint(lat=12.9816, lng=77.5946)
    route = Route(points=[p1, p2], distance_m=1111.0, duration_s=120.0, source="test")

    corridor = engine.get_route_corridor(route, corridor_width_m=30.0)

    # Point exactly midway on the route segment
    p_on_route = (12.9766, 77.5946)
    assert engine.is_point_in_corridor(p_on_route[0], p_on_route[1], corridor) is True

    # Point 15 meters to the East (within 30m corridor)
    # At lat 12.9766, 15m east is approx 15 / (111139 * cos(12.9766)) degrees lng
    deg_offset_15m = 15.0 / (111139.0 * 0.9744)
    p_near = (12.9766, 77.5946 + deg_offset_15m)
    dist_near = engine.distance_to_corridor_m(p_near[0], p_near[1], corridor)
    assert dist_near < 20.0
    assert engine.is_point_in_corridor(p_near[0], p_near[1], corridor) is True

    # Point 200 meters away (outside 30m corridor)
    deg_offset_200m = 200.0 / (111139.0 * 0.9744)
    p_far = (12.9766, 77.5946 + deg_offset_200m)
    dist_far = engine.distance_to_corridor_m(p_far[0], p_far[1], corridor)
    assert dist_far > 150.0
    assert engine.is_point_in_corridor(p_far[0], p_far[1], corridor) is False


def test_osrm_mocked_success():
    engine = OSRMRouteEngine(base_url="http://mock-osrm.local")

    mock_geojson = {
        "code": "Ok",
        "routes": [
            {
                "distance": 1450.5,
                "duration": 180.2,
                "geometry": {
                    "coordinates": [
                        [77.5946, 12.9716],
                        [77.5948, 12.9750],
                        [77.5950, 12.9800],
                    ]
                },
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(mock_geojson).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        route = engine.get_route(12.9716, 77.5946, 12.9800, 77.5950)

    assert route.source == "osrm"
    assert len(route.points) == 3
    assert route.points[0].lat == 12.9716
    assert route.points[0].lng == 77.5946
    assert route.points[2].lat == 12.9800
    assert route.distance_m == 1450.5
    assert route.duration_s == 180.2


def test_osrm_mocked_failure_raises_error():
    engine = OSRMRouteEngine(base_url="http://mock-osrm.local")

    # Simulate connection error / timeout
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        with pytest.raises(RoutingError) as exc_info:
            engine.get_route(12.9716, 77.5946, 12.9800, 77.5950)
        assert "Route service unavailable" in str(exc_info.value)

    # Simulate OSRM error code (e.g. NoRoute)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"code": "NoRoute", "message": "Impossible route"}).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(RoutingError) as exc_info:
            engine.get_route(12.9716, 77.5946, 12.9800, 77.5950)
        assert "Impossible route" in str(exc_info.value)


if __name__ == "__main__":
    test_corridor_geometry_and_membership()
    test_osrm_mocked_success()
    test_osrm_mocked_failure_raises_error()
    print("STEP 5 Route Engine tests PASSED successfully!")
