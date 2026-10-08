import gzip
import pickle
from math import floor
from pathlib import Path

from .geo import haversine_km


class Node:
    # slots save memory on the large graph
    __slots__ = ('id', 'lat', 'lon')

    def __init__(self, id, lat, lon):
        self.id = id
        self.lat = lat
        self.lon = lon

    def __setstate__(self, state):
        # load older saved graphs
        if isinstance(state, list):
            for name, value in zip(self.__slots__, state):
                setattr(self, name, value)
        else:
            for name, value in state[1].items():
                setattr(self, name, value)


class Edge:
    __slots__ = (
        "id",
        "source",
        "target",
        "distance_km",
        "eta_minutes",
        "road_class",
        "curve_score",
        "physical_id",
        "geometry",
        "motorway",
        "hill_score",
        "elevation_change_m",
        "speed_limit_kmh",
        "travel_speed_kmh",
    )

    def __init__(
        self,
        id,
        source,
        target,
        distance_km,
        eta_minutes,
        road_class,
        curve_score,
        physical_id,
        geometry,
        motorway=False,
        hill_score=0.0,
        elevation_change_m=0.0,
        speed_limit_kmh=0.0,
        travel_speed_kmh=0.0,
    ):
        self.id = id
        self.source = source
        self.target = target
        self.distance_km = distance_km
        self.eta_minutes = eta_minutes
        self.road_class = road_class
        self.curve_score = curve_score
        self.physical_id = physical_id
        self.geometry = geometry
        self.motorway = motorway
        self.hill_score = hill_score
        self.elevation_change_m = elevation_change_m
        self.speed_limit_kmh = speed_limit_kmh
        self.travel_speed_kmh = travel_speed_kmh

    def __setstate__(self, state):
        # load older saved graphs
        if isinstance(state, list):
            for name, value in zip(self.__slots__, state):
                setattr(self, name, value)
        else:
            for name, value in state[1].items():
                setattr(self, name, value)


class RoadGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.adjacency = {}
        self.max_speed_kmh = 130.0
        self.snap_node_ids = set()
        self._grid_size = 0.02
        self._snap_grid = {}

    def add_node(self, node):
        self.nodes[node.id] = node
        self.adjacency.setdefault(node.id, [])

    def add_edge(self, edge):
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError("Both edge nodes must be added before the edge")
        if edge.distance_km <= 0 or edge.eta_minutes <= 0:
            raise ValueError("Road edges need positive distance and ETA")
        if edge.id in self.edges:
            raise ValueError(f"Duplicate edge id {edge.id}")
        self.edges[edge.id] = edge
        self.adjacency[edge.source].append(edge.id)

    def outgoing(self, node_id):
        edges = []
        for edge_id in self.adjacency.get(node_id, ()):
            edges.append(self.edges[edge_id])
        return edges

    def nearest_node(self, lat, lon):
        if not self.nodes:
            raise ValueError("The graph is empty")

        candidates = set()
        grid = self._snap_grid
        grid_size = self._grid_size
        if grid:
            centre_row = floor(lat / grid_size)
            centre_col = floor(lon / grid_size)
            # search outward through nearby cells
            for ring in range(7):
                for row in range(centre_row - ring, centre_row + ring + 1):
                    for col in range(centre_col - ring, centre_col + ring + 1):
                        inside_row = row not in {
                            centre_row - ring, centre_row + ring
                        }
                        inside_col = col not in {
                            centre_col - ring, centre_col + ring
                        }
                        # inner cells were checked already
                        if ring and inside_row and inside_col:
                            continue
                        candidates.update(grid.get((row, col), ()))
                if candidates and ring >= 1:
                    break

        if not candidates:
            candidates = self.snap_node_ids or set(self.nodes)

        best_id = -1
        best_distance = float("inf")
        for node_id in candidates:
            node = self.nodes[node_id]
            distance = haversine_km(lat, lon, node.lat, node.lon)
            if distance < best_distance:
                best_id = node.id
                best_distance = distance
        return best_id, best_distance

    def prepare_snapping(self):
        if not self.nodes:
            return 0
        reverse = {node_id: [] for node_id in self.nodes}
        degree = {node_id: len(self.adjacency.get(node_id, ())) for node_id in self.nodes}
        for edge in self.edges.values():
            reverse[edge.target].append(edge.source)
            degree[edge.target] += 1

        seed = max(degree, key=degree.get)

        def reachable(start, neighbours):
            seen = {start}
            stack = [start]
            while stack:
                node_id = stack.pop()
                for next_id in neighbours(node_id):
                    if next_id not in seen:
                        seen.add(next_id)
                        stack.append(next_id)
            return seen

        forward = reachable(
            seed,
            lambda node_id: (
                self.edges[edge_id].target for edge_id in self.adjacency.get(node_id, ())
            ),
        )
        backward = reachable(seed, lambda node_id: iter(reverse.get(node_id, ())))
        # keep nodes reachable both ways
        self.snap_node_ids = forward & backward
        self._snap_grid = {}
        for node_id in self.snap_node_ids:
            node = self.nodes[node_id]
            cell = (floor(node.lat / self._grid_size), floor(node.lon / self._grid_size))
            self._snap_grid.setdefault(cell, []).append(node_id)
        return len(self.snap_node_ids)

    def save(self, path):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(target, "wb", compresslevel=5) as output:
            pickle.dump(self, output, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path):
        with gzip.open(path, "rb") as source:
            graph = pickle.load(source)
        if not isinstance(graph, cls):
            raise TypeError("Saved file does not contain a RoadGraph")
        return graph
