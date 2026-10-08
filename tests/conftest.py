import pytest

from route_planner.graph import Edge, Node, RoadGraph


@pytest.fixture
def choice_graph():
    graph = RoadGraph()
    points = {
        0: (49.00, 15.00),
        1: (49.00, 15.01),
        2: (49.01, 15.01),
        3: (49.00, 15.03),
        4: (48.99, 15.01),
    }
    for node_id, (lat, lon) in points.items():
        graph.add_node(Node(node_id, lat, lon))

    def add(edge_id, source, target, distance, eta, road, curve):
        a = points[source]
        b = points[target]
        graph.add_edge(Edge(edge_id, source, target, distance, eta, road, curve, str(edge_id), (a, b)))

    # fast primary road
    add(0, 0, 1, 2.0, 5.0, "primary", 0.05)
    add(1, 1, 3, 2.0, 5.0, "primary", 0.05)
    # curvy minor road
    add(2, 0, 2, 2.4, 6.0, "unclassified", 0.90)
    add(3, 2, 3, 2.4, 6.0, "unclassified", 0.90)
    # slower and worse
    add(4, 0, 4, 2.2, 7.0, "secondary", 0.20)
    add(5, 4, 3, 2.2, 7.0, "secondary", 0.20)
    return graph
