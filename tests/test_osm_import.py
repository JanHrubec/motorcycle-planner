from __future__ import annotations

import struct

from route_planner.graph import RoadGraph
from route_planner.osm_import import import_pbf


def test_small_osm_file_builds_directed_graph(tmp_path):
    output = tmp_path / "graph.pkl.gz"
    report = import_pbf("tests/tiny.osm", output)
    graph = RoadGraph.load(output)

    assert report["nodes"] == 5
    assert report["edges"] == 6  # two two-way segments and two one-way segments
    assert report["counts"]["excluded_highway"] == 1
    assert report["counts"]["ways_with_parsed_speed"] == 1
    assert report["counts"]["ways_with_speed_fallback"] == 1
    assert len(graph.outgoing(3)) == 2
    assert all(edge.target != 3 for edge in graph.outgoing(4))
    assert report["main_routing_core_nodes"] == 3
    snapped, _ = graph.nearest_node(49.0101, 15.0199)
    assert snapped == 3  # nodes 4 and 5 are outside the connected core
    assert all(edge.travel_speed_kmh <= edge.speed_limit_kmh for edge in graph.edges.values())
    assert output.exists()
    assert (tmp_path / "graph-report.json").exists()


def test_import_adds_hills_when_elevation_is_available(tmp_path):
    elevations = tmp_path / "elevation"
    elevations.mkdir()
    side = 101
    heights = [(side - row) * 10 for row in range(side) for _ in range(side)]
    (elevations / "N49E015.hgt").write_bytes(struct.pack(f">{len(heights)}h", *heights))

    output = tmp_path / "graph.pkl.gz"
    report = import_pbf("tests/tiny.osm", output, elevations)
    graph = RoadGraph.load(output)

    assert report["elevation_tiles"] == 1
    assert any(edge.hill_score > 0 for edge in graph.edges.values())
    assert any(edge.elevation_change_m > 0 for edge in graph.edges.values())
    assert any(edge.elevation_change_m < 0 for edge in graph.edges.values())
