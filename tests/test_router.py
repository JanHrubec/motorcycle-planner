from __future__ import annotations

from dataclasses import replace

import pytest

from route_planner.router import Label, Route, RouteSettings, Router


def exact_settings(detour: float = 30) -> RouteSettings:
    return RouteSettings(
        detour_percent=detour,
        curve_preference=50,
        hill_preference=50,
        road_preference=50,
        town_preference=30,
    )


def test_fastest_a_star(choice_graph):
    result = Router(choice_graph).fastest_path(0, 3, exact_settings())
    assert result is not None
    edges, eta, debug = result
    assert edges == [0, 1]
    assert eta == pytest.approx(10)
    assert debug["fastest_expanded"] > 0


def test_label_search_keeps_the_useful_tradeoff(choice_graph):
    routes, debug = Router(choice_graph).search(0, 3, exact_settings(detour=50))
    paths = {tuple(route.edge_ids) for route in routes}
    assert (0, 1) in paths
    assert (2, 3) in paths
    assert (4, 5) not in paths
    assert debug["labels_created"] > 0
    assert debug["dominance_removed"] > 0


def test_eta_ceiling_removes_scenic_route(choice_graph):
    routes, debug = Router(choice_graph).search(0, 3, exact_settings(detour=10))
    assert [route.edge_ids for route in routes] == [[0, 1]]
    assert debug["eta_limit"] == pytest.approx(11)


def test_route_statistics(choice_graph):
    router = Router(choice_graph)
    routes, _ = router.search(0, 3, exact_settings())
    scenic = next(route for route in routes if route.edge_ids == [2, 3])
    assert scenic.distance_km == pytest.approx(4.8)
    assert scenic.eta_minutes == pytest.approx(12)
    assert scenic.twistiness == pytest.approx(90)
    assert scenic.hilliness == 0
    assert scenic.major_road_percent == 0
    assert scenic.coordinates[0] == (49.0, 15.0)
    assert scenic.coordinates[-1] == (49.0, 15.03)


def test_overlap_uses_physical_road_ids(choice_graph):
    router = Router(choice_graph)
    routes, _ = router.search(0, 3, exact_settings())
    assert router.route_overlap(routes[0], routes[1]) == 0
    assert router.route_separation(routes[0], routes[1]) > 0.4
    assert router.meaningfully_different(routes[0], routes[1])


def test_selected_alternatives_improve_quality_and_are_distinct(choice_graph):
    router = Router(choice_graph)
    routes, _ = router.search(0, 3, exact_settings(detour=50))
    fastest = routes[0]

    for index, route in enumerate(routes[1:], start=1):
        fastest_quality = fastest.penalty / fastest.distance_km
        route_quality = route.penalty / route.distance_km
        assert route_quality < fastest_quality
        assert all(
            router.meaningfully_different(route, earlier)
            for earlier in routes[:index]
        )


def test_preference_controls_are_independent_and_strong(choice_graph):
    router = Router(choice_graph)
    bendy = choice_graph.edges[2]
    plain = choice_graph.edges[0]
    settings = exact_settings()
    assert router.edge_penalty(bendy, settings) < router.edge_penalty(plain, settings)

    no_bends = RouteSettings(
        detour_percent=30,
        curve_preference=0,
        hill_preference=0,
        road_preference=0,
        town_preference=0,
    )
    assert router.edge_penalty(bendy, no_bends) > router.edge_penalty(plain, no_bends)

    more_detour = RouteSettings(
        detour_percent=60,
        curve_preference=50,
        hill_preference=50,
        road_preference=50,
        town_preference=30,
    )
    assert router.edge_penalty(bendy, more_detour) == router.edge_penalty(bendy, settings)

    hilly = replace(bendy, hill_score=1)
    hills_off = replace(settings, hill_preference=0)
    hills_on = replace(settings, hill_preference=100)
    assert router.edge_penalty(hilly, hills_on) < router.edge_penalty(hilly, hills_off)


def test_zero_preferences_do_not_change_an_edge(choice_graph):
    router = Router(choice_graph)
    edge = choice_graph.edges[0]
    zero = RouteSettings(
        detour_percent=60,
        curve_preference=0,
        hill_preference=0,
        road_preference=0,
        town_preference=0,
    )

    bendy = replace(edge, curve_score=1)
    hilly = replace(edge, hill_score=1)
    minor = replace(edge, road_class="unclassified")
    town = replace(edge, road_class="residential")
    expected = edge.distance_km
    assert router.edge_penalty(bendy, zero) == pytest.approx(expected)
    assert router.edge_penalty(hilly, zero) == pytest.approx(expected)
    assert router.edge_penalty(minor, zero) == pytest.approx(expected)
    assert router.edge_penalty(town, zero) == pytest.approx(expected)

    routes, debug = router.search(0, 3, zero)
    assert [route.edge_ids for route in routes] == [[0, 1]]
    assert debug["labels_created"] == 0


def test_one_preference_gets_stronger_as_its_slider_rises(choice_graph):
    router = Router(choice_graph)
    edge = choice_graph.edges[2]
    low = RouteSettings(
        curve_preference=5,
        hill_preference=0,
        road_preference=0,
        town_preference=0,
    )
    high = replace(low, curve_preference=100)
    assert router.edge_penalty(edge, high) < router.edge_penalty(edge, low)


def test_hill_preference_changes_the_whole_route(choice_graph):
    choice_graph.edges[2] = replace(choice_graph.edges[2], hill_score=1)
    choice_graph.edges[3] = replace(choice_graph.edges[3], hill_score=1)
    off = RouteSettings(
        detour_percent=30,
        curve_preference=0,
        hill_preference=0,
        road_preference=0,
        town_preference=0,
    )
    on = replace(off, hill_preference=100)

    routes_off, _ = Router(choice_graph).search(0, 3, off)
    routes_on, _ = Router(choice_graph).search(0, 3, on)

    assert [route.edge_ids for route in routes_off] == [[0, 1]]
    assert (2, 3) in {tuple(route.edge_ids) for route in routes_on}


def test_every_result_stays_inside_the_detour_cap(choice_graph):
    settings = exact_settings(detour=60)
    routes, debug = Router(choice_graph).search(0, 3, settings)

    assert routes
    assert all(route.eta_minutes <= debug["eta_limit"] for route in routes)


def test_zero_detour_allows_only_the_fastest_eta(choice_graph):
    routes, debug = Router(choice_graph).search(
        0, 3, exact_settings(detour=0)
    )

    assert [route.edge_ids for route in routes] == [[0, 1]]
    assert debug["eta_limit"] == debug["fastest_eta"]


def test_more_detour_can_reveal_a_third_tradeoff(choice_graph):
    for edge_id in (4, 5):
        choice_graph.edges[edge_id] = replace(
            choice_graph.edges[edge_id],
            road_class="unclassified",
            curve_score=1,
        )
    base = RouteSettings(
        curve_preference=100,
        hill_preference=0,
        road_preference=0,
        town_preference=0,
    )

    short, _ = Router(choice_graph).search(
        0, 3, replace(base, detour_percent=20)
    )
    long, _ = Router(choice_graph).search(
        0, 3, replace(base, detour_percent=60)
    )

    assert len(short) == 2
    assert [route.edge_ids for route in long] == [[0, 1], [2, 3], [4, 5]]


def test_selection_keeps_the_largest_different_set(choice_graph, monkeypatch):
    router = Router(choice_graph)
    candidates = [
        Route([number], 10 + number, 9 - number / 2, distance_km=10)
        for number in range(4)
    ]

    def different(first, second):
        pair = {first.edge_ids[0], second.edge_ids[0]}
        return pair not in ({1, 2}, {1, 3})

    monkeypatch.setattr(router, "meaningfully_different", different)
    selected = router._select_routes(candidates)

    assert [route.edge_ids for route in selected] == [[0], [2], [3]]


def test_disconnected_direction_reports_no_path(choice_graph):
    routes, debug = Router(choice_graph).search(
        3, 0, exact_settings()
    )

    assert routes == []
    assert debug["reason"] == "no_path"


def test_label_cap_keeps_fast_and_low_cost_extremes(choice_graph):
    router = Router(choice_graph)
    labels = [
        # eta rises while cost falls, so none dominates another
        Label(i, 5 + i, 12 - i, None, None)
        for i in range(8)
    ]
    kept = list(range(8))

    removed = router._trim_labels(kept, labels)

    assert removed == 2
    assert len(kept) == 6
    assert 0 in kept  # fastest
    assert 7 in kept  # lowest preference cost
