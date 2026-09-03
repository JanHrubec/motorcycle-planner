import json
import re
from bisect import bisect_left, bisect_right
from collections import Counter
from pathlib import Path
from time import perf_counter

import osmium

from .elevation import ElevationTiles
from .geo import bearing_change, bearing_degrees, haversine_km
from .graph import Edge, Node, RoadGraph

ALLOWED_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
}

UNPAVED_SURFACES = {
    "unpaved",
    "gravel",
    "fine_gravel",
    "dirt",
    "earth",
    "grass",
    "ground",
    "mud",
    "sand",
    "compacted",
}

ROAD_SPEEDS = {
    "motorway": 90,
    "motorway_link": 45,
    "trunk": 85,
    "trunk_link": 40,
    "primary": 65,
    "primary_link": 30,
    "secondary": 55,
    "secondary_link": 25,
    "tertiary": 40,
    "tertiary_link": 20,
    "unclassified": 25,
    "residential": 25,
    "living_street": 10,
}

CZ_SPEEDS = {
    "cz:urban": 50,
    "cz:rural": 90,
    "cz:motorway": 130,
    "cz:motorroad": 110,
    "cz:trunk": 110,
    "cz:urban_motorway": 80,
    "cz:urban_trunk": 80,
    "cz:living_street": 20,
    "cz:pedestrian_zone": 20,
}

BLOCKED_ACCESS = {"no", "private"}
CURVE_DEGREES_PER_KM = 90.0
HILL_WINDOW_KM = 0.15


def motorcycle_allowed(tags):
    # use the most specific access tag
    for key in ("motorcycle", "motor_vehicle", "vehicle", "access"):
        value = tags.get(key)
        if value:
            return value not in BLOCKED_ACCESS
    return True


def parse_speed(value):
    if not value:
        return None
    first = value.split(";")[0].strip().lower()
    if first in CZ_SPEEDS:
        return float(CZ_SPEEDS[first])
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mph)?", first)
    if not match:
        return None
    speed = float(match.group(1))
    if match.group(2):
        speed *= 1.609344
    return speed if 5 <= speed <= 160 else None


def legal_speed(tags, highway):
    speed = parse_speed(tags.get("maxspeed"))
    if speed is not None:
        return speed

    # some ways store the legal context separately from maxspeed
    for key in ("maxspeed:type", "source:maxspeed", "zone:traffic"):
        speed = parse_speed(tags.get(key))
        if speed is not None:
            return speed

    if highway.startswith("motorway"):
        return 130.0
    if tags.get("motorroad") == "yes":
        return 110.0
    if highway.startswith("trunk") and tags.get("motorroad") != "no":
        return 110.0
    if highway == "living_street":
        return 20.0
    if highway == "residential":
        return 50.0
    return 90.0


def road_speed(tags, highway):
    limit = legal_speed(tags, highway)
    # use the road estimate unless a lower limit is posted
    return min(limit, float(ROAD_SPEEDS[highway]))


def segment_curve(points, index, distance_km):
    # use the bends touching this short osm segment
    changes = []
    if index > 0:
        first = bearing_degrees(*points[index - 1], *points[index])
        second = bearing_degrees(*points[index], *points[index + 1])
        change = bearing_change(first, second)
        if change >= 5:
            changes.append(min(change, 120))
    if index + 2 < len(points):
        first = bearing_degrees(*points[index], *points[index + 1])
        second = bearing_degrees(*points[index + 1], *points[index + 2])
        change = bearing_change(first, second)
        if change >= 5:
            changes.append(min(change, 120))
    if not changes:
        return 0.0
    local_change = sum(changes) / len(changes)
    return min(1.0, local_change / max(distance_km * CURVE_DEGREES_PER_KM, 20.0))


def road_hills(points, distances, terrain):
    if terrain is None:
        return [None] * len(points), [0.0] * len(distances)

    # a window is steadier than slopes on very short osm edges
    heights = [terrain.at(*point) for point in points]
    along = [0.0]
    for distance in distances:
        along.append(along[-1] + distance)

    hills = []
    for index in range(len(distances)):
        middle = (along[index] + along[index + 1]) / 2
        left = min(index, bisect_left(along, middle - HILL_WINDOW_KM))
        right = max(
            index + 1, bisect_right(along, middle + HILL_WINDOW_KM) - 1
        )
        levels = [
            height for height in heights[left:right + 1] if height is not None
        ]
        if len(levels) < 2:
            hills.append(0.0)
            continue
        rise = max(levels) - min(levels)
        distance = along[right] - along[left]
        grade = rise / max(distance * 1000, 120)
        hills.append(min(1.0, grade / 0.08))
    return heights, hills


class RoadHandler(osmium.SimpleHandler):
    def __init__(self, terrain=None):
        super().__init__()
        self.graph = RoadGraph()
        self.terrain = terrain
        self.next_edge_id = 0
        self.counts = Counter()
        self.fastest_speed = 0.0

    def way(self, way):
        self.counts["ways_seen"] += 1
        highway = way.tags.get("highway")
        if highway not in ALLOWED_HIGHWAYS:
            self.counts["excluded_highway"] += 1
            return
        if not motorcycle_allowed(way.tags):
            self.counts["excluded_access"] += 1
            return
        surface = (way.tags.get("surface") or "").lower()
        if surface in UNPAVED_SURFACES:
            self.counts["excluded_surface"] += 1
            return

        try:
            refs = [node.ref for node in way.nodes]
            points = [(node.lat, node.lon) for node in way.nodes]
        except osmium.InvalidLocationError:
            self.counts["excluded_missing_location"] += 1
            return
        if len(points) < 2:
            self.counts["excluded_short_way"] += 1
            return

        limit = legal_speed(way.tags, highway)
        speed = road_speed(way.tags, highway)
        speed_keys = (
            "maxspeed:motorcycle", "maxspeed", "maxspeed:type",
            "source:maxspeed", "zone:traffic",
        )
        if any(parse_speed(way.tags.get(key)) is not None for key in speed_keys):
            self.counts["ways_with_parsed_speed"] += 1
        else:
            self.counts["ways_with_speed_fallback"] += 1
        self.fastest_speed = max(self.fastest_speed, speed)
        one_way_value = (way.tags.get("oneway") or "").lower()
        is_roundabout = way.tags.get("junction") == "roundabout"
        reverse_only = one_way_value == "-1"
        one_way = one_way_value in {"yes", "1", "true"} or is_roundabout or reverse_only
        road_class = highway.removesuffix("_link")
        distances = [
            haversine_km(*points[index], *points[index + 1])
            for index in range(len(points) - 1)
        ]
        heights, hills = road_hills(points, distances, self.terrain)

        for node_ref, point in zip(refs, points):
            if node_ref not in self.graph.nodes:
                self.graph.add_node(Node(node_ref, point[0], point[1]))

        for index in range(len(refs) - 1):
            distance = distances[index]
            if distance <= 0:
                self.counts["excluded_zero_length"] += 1
                continue
            curve = segment_curve(points, index, distance)
            eta = distance / speed * 60
            physical_id = f"{way.id}:{index}"
            first_height = heights[index]
            second_height = heights[index + 1]
            height_change = 0.0
            if first_height is not None and second_height is not None:
                height_change = second_height - first_height
            hill = hills[index]
            forward = not reverse_only
            backward = not one_way or reverse_only

            if forward:
                self._add_edge(
                    refs[index], refs[index + 1], points[index], points[index + 1],
                    distance, eta, road_class, curve, hill, height_change, physical_id,
                    limit, speed,
                )
            if backward:
                self._add_edge(
                    refs[index + 1], refs[index], points[index + 1], points[index],
                    distance, eta, road_class, curve, hill, -height_change, physical_id,
                    limit, speed,
                )
        self.counts["ways_retained"] += 1

    def _add_edge(self, source, target, first, second, distance, eta, road_class, curve, hill, height_change, physical_id, speed_limit, travel_speed):
        self.graph.add_edge(
            Edge(
                id=self.next_edge_id,
                source=source,
                target=target,
                distance_km=distance,
                eta_minutes=eta,
                road_class=road_class,
                curve_score=curve,
                physical_id=physical_id,
                geometry=(first, second),
                motorway=road_class in {"motorway", "trunk"},
                hill_score=hill,
                elevation_change_m=height_change,
                speed_limit_kmh=speed_limit,
                travel_speed_kmh=travel_speed,
            )
        )
        self.next_edge_id += 1
        self.counts["directed_edges"] += 1


def import_pbf(input_path, output_path, elevation_dir = None):
    input_file = Path(input_path)
    output_file = Path(output_path)
    if not input_file.exists():
        raise FileNotFoundError(input_file)

    started = perf_counter()
    terrain = ElevationTiles(elevation_dir) if elevation_dir else None
    handler = RoadHandler(terrain)
    handler.apply_file(str(input_file), locations=True, idx="flex_mem")
    handler.graph.max_speed_kmh = max(handler.fastest_speed, 90.0)
    snap_nodes = handler.graph.prepare_snapping()
    handler.graph.save(output_file)
    elapsed = perf_counter() - started

    report = {
        "input": str(input_file),
        "input_bytes": input_file.stat().st_size,
        "output": str(output_file),
        "output_bytes": output_file.stat().st_size,
        "nodes": len(handler.graph.nodes),
        "edges": len(handler.graph.edges),
        "main_routing_core_nodes": snap_nodes,
        "max_speed_kmh": handler.graph.max_speed_kmh,
        "elevation_tiles": len(terrain.loaded) if terrain else 0,
        "elapsed_seconds": round(elapsed, 3),
        "counts": dict(sorted(handler.counts.items())),
    }
    report_path = output_file.with_name(output_file.name.removesuffix(".pkl.gz") + "-report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
