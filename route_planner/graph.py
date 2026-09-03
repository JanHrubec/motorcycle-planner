import gzip
import pickle
from dataclasses import dataclass
from math import floor
from pathlib import Path

from .geo import haversine_km


@dataclass(frozen=True, slots=True)
class Node:
    id: int
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Edge:
    id: int
    source: int
    target: int
    distance_km: float
    eta_minutes: float
    road_class: str
    curve_score: float
    physical_id: str
    geometry: tuple[tuple[float, float], ...]
    motorway: bool = False
    hill_score: float = 0.0
    elevation_change_m: float = 0.0
    speed_limit_kmh: float = 0.0
    travel_speed_kmh: float = 0.0


class RoadGraph:
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.adjacency = {}
        self.max_speed_kmh = 130.0
        self.snap_node_ids = set()
        self._grid_size = 0.02
        self._snap_grid = {}

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        self.adjacency.setdefault(node.id, [])

    def add_edge(self, edge: Edge) -> None:
        if edge.source not in self.nodes or edge.target not in self.nodes:
            raise ValueError("Both edge nodes must be added before the edge")
        if edge.distance_km <= 0 or edge.eta_minutes <= 0:
            raise ValueError("Road edges need positive distance and ETA")
        if edge.id in self.edges:
            raise ValueError(f"Duplicate edge id {edge.id}")
        self.edges[edge.id] = edge
        self.adjacency[edge.source].append(edge.id)

    def outgoing(self, node_id):
        return [self.edges[edge_id] for edge_id in self.adjacency.get(node_id, ())]

    def nearest_node(self, lat, lon):
        if not self.nodes:
            raise ValueError("The graph is empty")

        candidates = set()
        grid = self._snap_grid
        grid_size = self._grid_size
        if grid:
            # check nearby grid rings instead of every road node
            centre_row = floor(lat / grid_size)
            centre_col = floor(lon / grid_size)
            for ring in range(7):
                for row in range(centre_row - ring, centre_row + ring + 1):
                    for col in range(centre_col - ring, centre_col + ring + 1):
                        inside_row = row not in {
                            centre_row - ring, centre_row + ring
                        }
                        inside_col = col not in {
                            centre_col - ring, centre_col + ring
                        }
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
        """index the main connected road section used for snapping"""
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
        # snapping to this intersection avoids one-way pieces with no route back
        self.snap_node_ids = forward & backward
        self._snap_grid = {}
        for node_id in self.snap_node_ids:
            node = self.nodes[node_id]
            cell = (floor(node.lat / self._grid_size), floor(node.lon / self._grid_size))
            self._snap_grid.setdefault(cell, []).append(node_id)
        return len(self.snap_node_ids)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(target, "wb", compresslevel=5) as output:
            pickle.dump(self, output, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: str | Path) -> "RoadGraph":
        with gzip.open(path, "rb") as source:
            graph = pickle.load(source)
        if not isinstance(graph, cls):
            raise TypeError("Saved file does not contain a RoadGraph")
        return graph
