import pytest

from route_planner.router import Label, Route, RouteSettings, Router


def settings(detour=30):
    return RouteSettings(detour, 50, 50, 50, 30)


def test_fastest_route(choice_graph):
    edges, eta, _ = Router(choice_graph).fastest_path(0, 3, settings())
    assert edges == [0, 1]
    assert eta == 10


def test_route_choices(choice_graph):
    router = Router(choice_graph)
    routes, debug = router.search(0, 3, settings(50))
    assert [route.edge_ids for route in routes] == [[0, 1], [2, 3]]
    fast, scenic = routes
    assert scenic.penalty / scenic.distance_km < fast.penalty / fast.distance_km
    assert router.route_overlap(fast, scenic) == 0
    assert router.meaningfully_different(fast, scenic)
    for route in routes:
        assert route.eta_minutes <= debug["eta_limit"]


def test_detour_limit(choice_graph):
    router = Router(choice_graph)
    for detour in (0, 10):
        routes, debug = router.search(0, 3, settings(detour))
        assert [route.edge_ids for route in routes] == [[0, 1]]
        assert debug["eta_limit"] == pytest.approx(10 * (1 + detour / 100))


def test_route_stats(choice_graph):
    routes, _ = Router(choice_graph).search(0, 3, settings())
    scenic = routes[1]
    assert scenic.distance_km == pytest.approx(4.8)
    assert scenic.eta_minutes == 12
    assert scenic.twistiness == pytest.approx(90)
    assert scenic.hilliness == 0
    assert scenic.major_road_percent == 0
    assert scenic.coordinates[0] == (49.0, 15.0)
    assert scenic.coordinates[-1] == (49.0, 15.03)


def test_preferences(choice_graph):
    router = Router(choice_graph)
    bendy = choice_graph.edges[2]
    plain = choice_graph.edges[0]
    prefs = settings()
    original = router.edge_penalty(bendy, prefs)
    assert original < router.edge_penalty(plain, prefs)
    prefs.detour_percent = 60
    assert router.edge_penalty(bendy, prefs) == original
    prefs.curve_preference = 100
    assert router.edge_penalty(bendy, prefs) < original


def test_preferences_off(choice_graph):
    prefs = RouteSettings(60, 0, 0, 0, 0)
    router = Router(choice_graph)
    for edge in choice_graph.edges.values():
        assert router.edge_penalty(edge, prefs) == edge.distance_km
    routes, _ = router.search(0, 3, prefs)
    assert [route.edge_ids for route in routes] == [[0, 1]]


def test_hills(choice_graph):
    choice_graph.edges[2].hill_score = 1
    choice_graph.edges[3].hill_score = 1
    prefs = RouteSettings(30, 0, 0, 0, 0)
    router = Router(choice_graph)
    routes, _ = router.search(0, 3, prefs)
    assert [route.edge_ids for route in routes] == [[0, 1]]
    prefs.hill_preference = 100
    routes, _ = router.search(0, 3, prefs)
    assert [route.edge_ids for route in routes] == [[0, 1], [2, 3]]


def test_more_detour(choice_graph):
    for edge_id in (4, 5):
        choice_graph.edges[edge_id].road_class = "unclassified"
        choice_graph.edges[edge_id].curve_score = 1
    prefs = RouteSettings(20, 100, 0, 0, 0)
    router = Router(choice_graph)
    routes, _ = router.search(0, 3, prefs)
    assert len(routes) == 2
    prefs.detour_percent = 60
    routes, _ = router.search(0, 3, prefs)
    assert [route.edge_ids for route in routes] == [[0, 1], [2, 3], [4, 5]]


def test_alternative_selection(choice_graph, monkeypatch):
    router = Router(choice_graph)
    routes = [Route([i], 10 + i, 9 - i / 2, distance_km=10) for i in range(4)]

    # route 1 conflicts with both other alternatives
    def different(first, second):
        pair = {first.edge_ids[0], second.edge_ids[0]}
        return pair not in ({1, 2}, {1, 3})

    monkeypatch.setattr(router, "meaningfully_different", different)
    selected = router._select_routes(routes)
    assert [route.edge_ids for route in selected] == [[0], [2], [3]]


def test_no_path(choice_graph):
    routes, debug = Router(choice_graph).search(3, 0, settings())
    assert routes == []
    assert debug["reason"] == "no_path"


def test_label_limit(choice_graph):
    # time rises while penalty falls
    labels = [Label(i, 5 + i, 12 - i, None, None) for i in range(8)]
    kept = list(range(8))
    removed = Router(choice_graph)._trim_labels(kept, labels)
    assert removed == 2
    assert len(kept) == 6
    assert 0 in kept  # fastest
    assert 7 in kept  # lowest penalty
