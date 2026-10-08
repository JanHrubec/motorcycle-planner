from xml.etree import ElementTree

import pytest

from app import create_app
from route_planner.gpx import make_gpx
from route_planner.service import RequestError, RouteService


def valid_request():
    return {
        "start": {"lat": 49.0, "lon": 15.0},
        "target": {"lat": 49.0, "lon": 15.03},
        "detour_percent": 30,
        "curve_preference": 50,
        "hill_preference": 50,
        "road_preference": 50,
        "town_preference": 30,
        "avoid_motorways": False,
    }


def test_service_returns_serialized_routes(choice_graph):
    result = RouteService(choice_graph).route(valid_request())
    assert len(result["routes"]) == 2
    assert result["routes"][0]["stats"]["eta_minutes"] == 10
    assert result["routes"][1]["stats"]["detour_percent"] == 20
    assert result["snapped"]["start"]["id"] == 0


def test_same_point_is_rejected(choice_graph):
    request = valid_request()
    request["target"] = request["start"]
    with pytest.raises(RequestError, match="same road junction"):
        RouteService(choice_graph).route(request)


def test_far_point_is_rejected(choice_graph):
    request = valid_request()
    request["start"] = {"lat": 48.0, "lon": 14.0}
    with pytest.raises(RequestError, match="supported road network"):
        RouteService(choice_graph).route(request)


def test_boolean_setting_is_validated(choice_graph):
    request = valid_request()
    request["avoid_motorways"] = "no"
    with pytest.raises(RequestError, match="true or false"):
        RouteService(choice_graph).route(request)

def test_detour_range(choice_graph):
    request = valid_request()
    service = RouteService(choice_graph)
    request["detour_percent"] = 60
    assert service.route(request)["settings"]["detour_percent"] == 60
    request["detour_percent"] = 65
    with pytest.raises(RequestError, match="between 0 and 60"):
        service.route(request)


def test_motorway_filter_gives_a_recovery_hint(choice_graph):
    for edge in choice_graph.edges.values():
        edge.motorway = True
    request = valid_request()
    request["avoid_motorways"] = True
    with pytest.raises(RequestError, match="Turn off No motorways"):
        RouteService(choice_graph).route(request)


def test_api_and_gpx_download(choice_graph):
    app = create_app(RouteService(choice_graph))
    client = app.test_client()
    response = client.post("/api/routes", json=valid_request())
    assert response.status_code == 200
    route = response.get_json()["routes"][0]

    export = client.post("/api/gpx", json={"edge_ids": route["edge_ids"], "name": "test route"})
    assert export.status_code == 200
    assert export.headers["Content-Type"].startswith("application/gpx+xml")
    root = ElementTree.fromstring(export.data)
    assert root.tag.endswith("gpx")
    points = root.findall(".//{http://www.topografix.com/GPX/1/1}trkpt")
    assert len(points) == 3
    assert float(points[0].attrib["lat"]) == 49.0
    assert float(points[-1].attrib["lon"]) == 15.03


def test_gpx_rejects_too_few_points():
    with pytest.raises(ValueError):
        make_gpx([(49.0, 15.0)], "bad")


def test_api_validation_error(choice_graph):
    app = create_app(RouteService(choice_graph))
    client = app.test_client()
    response = client.post("/api/routes", json={})
    assert response.status_code == 400
    assert "Choose a start" in response.get_json()["error"]
