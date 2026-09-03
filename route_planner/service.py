from dataclasses import asdict
from pathlib import Path

from .graph import RoadGraph
from .router import MAX_DETOUR, Route, RouteSettings, Router


class RequestError(ValueError):
    pass


def load_graph():
    path = Path("data/graph.pkl.gz")
    if not path.exists():
        raise FileNotFoundError(
            f"Road graph not found at {path}. Run preprocess_osm.py first"
        )
    return RoadGraph.load(path)


def read_number(data, key, low, high):
    try:
        value = float(data[key])
    except (KeyError, TypeError, ValueError) as error:
        raise RequestError(f"{key.replace('_', ' ').capitalize()} must be a number") from error
    if not low <= value <= high:
        label = key.replace("_", " ").capitalize()
        raise RequestError(f"{label} must be between {low:g} and {high:g}")
    return value


def read_point(data, key):
    point = data.get(key)
    if not isinstance(point, dict):
        raise RequestError(f"Choose a {key} point on the map")
    lat = read_number(point, "lat", -90, 90)
    lon = read_number(point, "lon", -180, 180)
    return lat, lon


def parse_settings(data):
    avoid_motorways = data.get("avoid_motorways", False)
    if not isinstance(avoid_motorways, bool):
        raise RequestError("Avoid motorways must be true or false")
    return RouteSettings(
        detour_percent=read_number(data, "detour_percent", 0, MAX_DETOUR),
        curve_preference=read_number(data, "curve_preference", 0, 100),
        hill_preference=read_number(data, "hill_preference", 0, 100),
        road_preference=read_number(data, "road_preference", 0, 100),
        town_preference=read_number(data, "town_preference", 0, 100),
        avoid_motorways=avoid_motorways,
    )


def serialize_route(route, fastest_eta):
    return {
        "edge_ids": route.edge_ids,
        "coordinates": [[lat, lon] for lat, lon in route.coordinates],
        "stats": {
            "distance_km": round(route.distance_km, 2),
            "eta_minutes": round(route.eta_minutes, 1),
            "detour_percent": round((route.eta_minutes / fastest_eta - 1) * 100, 1),
            "twistiness": round(route.twistiness, 1),
            "hilliness": round(route.hilliness, 1),
            "elevation_gain_m": round(route.elevation_gain_m),
            "major_road_percent": round(route.major_road_percent, 1),
            "town_road_percent": round(route.town_road_percent, 1),
        },
    }


class RouteService:
    def __init__(self, graph) -> None:
        self.graph = graph
        self.router = Router(graph)

    def route(self, data):
        start_lat, start_lon = read_point(data, "start")
        target_lat, target_lon = read_point(data, "target")
        settings = parse_settings(data)

        start_id, start_distance = self.graph.nearest_node(start_lat, start_lon)
        target_id, target_distance = self.graph.nearest_node(target_lat, target_lon)
        
        if start_distance > 0.5:
            raise RequestError(
                f"Start is {start_distance:.1f} km from the supported road network"
            )
        if target_distance > 0.5:
            raise RequestError(
                f"Destination is {target_distance:.1f} km from the supported road network"
            )
        if start_id == target_id:
            raise RequestError("Start and destination snap to the same road junction")

        routes, debug = self.router.search(start_id, target_id, settings)
        if not routes:
            if debug.get("reason") == "motorway_filter":
                raise RequestError(
                    "No route without motorways connects these points. "
                    "Turn off No motorways and try again"
                )
            raise RequestError("No permitted route connects these points")
        fastest_eta = min(route.eta_minutes for route in routes)
        return {
            "routes": [serialize_route(route, fastest_eta) for route in routes],
            "snapped": {
                "start": asdict(self.graph.nodes[start_id]),
                "target": asdict(self.graph.nodes[target_id]),
                "start_distance_km": round(start_distance, 3),
                "target_distance_km": round(target_distance, 3),
            },
            "settings": asdict(settings),
        }

    def edges_to_coordinates(self, edge_ids):
        if not edge_ids or not all(isinstance(item, int) for item in edge_ids):
            raise RequestError("Export request has no valid route edges")
        if any(item not in self.graph.edges for item in edge_ids):
            raise RequestError("Export request contains an unknown road edge")
        try:
            return self.router.route_coordinates(edge_ids)
        except ValueError as error:
            raise RequestError("Export request is not a continuous route") from error
