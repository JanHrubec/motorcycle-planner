import argparse
from time import perf_counter

from route_planner.graph import RoadGraph
from route_planner.router import RouteSettings, Router


CASES = [
    ((49.3961, 15.5912), (49.2149, 15.8817), "Jihlava -> Trebic"),
    ((49.3961, 15.5912), (49.5626, 15.9392), "Jihlava -> Zdar"),
    ((49.4313, 15.2234), (49.6079, 15.5807), "Pelhrimov -> Havlickuv Brod"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    load_started = perf_counter()
    graph = RoadGraph.load("data/graph.pkl.gz")

    print(
        f"Loaded {len(graph.nodes)} nodes and {len(graph.edges)} edges in {perf_counter() - load_started:.2f} s"
    )

    router = Router(graph)
    settings = RouteSettings(
        detour_percent=30,
        curve_preference=60,
        hill_preference=50,
        road_preference=40,
        town_preference=30,
    )

    for start, target, name in CASES:
        started = perf_counter()
        start_id, start_snap = graph.nearest_node(*start)
        target_id, target_snap = graph.nearest_node(*target)
        routes, details = router.search(start_id, target_id, settings)
        wall_ms = (perf_counter() - started) * 1000
        print(f"\n{name}")
        print(f"  snap distances: {start_snap:.3f} km, {target_snap:.3f} km")
        print(f"  routes: {len(routes)}, wall time: {wall_ms:.1f} ms")
        print(
            f"  labels: {details.get('labels_created')}, "
            f"expanded: {details.get('labels_expanded')}, "
            f"cap removals: {details.get('label_cap_removed')}"
        )
        for route in routes:
            print(
                f"    {route.distance_km:6.1f} km {route.eta_minutes:6.1f} min "
                f"bends={route.twistiness:4.1f} hills={route.hilliness:4.1f} "
                f"major={route.major_road_percent:4.1f}%"
            )

    hill_settings = RouteSettings(
        detour_percent=40,
        curve_preference=0,
        hill_preference=100,
        road_preference=0,
        town_preference=0,
    )
    print("\nHill-only checks")
    for start, target, name in CASES:
        start_id, _ = graph.nearest_node(*start)
        target_id, _ = graph.nearest_node(*target)
        routes, details = router.search(start_id, target_id, hill_settings)
        values = ", ".join(
            f"{route.eta_minutes:.1f} min/{route.hilliness:.1f} hills"
            for route in routes
        )
        print(f"  {name}: {values} ({details['elapsed_ms']:.0f} ms)")

    if args.sweep:
        print("\nDetour sweep")
        for start, target, name in CASES:
            print(f"  {name}")
            start_id, _ = graph.nearest_node(*start)
            target_id, _ = graph.nearest_node(*target)
            for detour in (10, 20, 35, 60):
                sweep_settings = RouteSettings(
                    detour_percent=detour,
                    curve_preference=60,
                    hill_preference=50,
                    road_preference=40,
                    town_preference=30,
                )
                routes, details = router.search(
                    start_id, target_id, sweep_settings
                )
                times = ", ".join(
                    f"{route.eta_minutes:.1f} min" for route in routes
                )
                print(
                    f"    {detour:2d}%: {len(routes)} route(s), {times} "
                    f"({details['elapsed_ms']:.0f} ms, "
                    f"{details['target_labels']} target labels)"
                )


if __name__ == "__main__":
    main()
