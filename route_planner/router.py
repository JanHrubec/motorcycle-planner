import heapq
from copy import copy
from itertools import count
from math import inf
from time import perf_counter

from .geo import haversine_km

ROAD_PENALTIES = {
    "motorway": 1.0,
    "trunk": 0.88,
    "primary": 0.68,
    "secondary": 0.38,
    "tertiary": 0.16,
    "unclassified": 0.06,
    "residential": 0.12,
    "living_street": 0.16,
}

MAJOR_CLASSES = {"motorway", "trunk", "primary"}
TOWN_CLASSES = {"residential", "living_street"}
LABEL_LIMIT = 6
DOMINANCE_MARGIN = 0.015
MAX_DETOUR = 60


class RouteSettings:
    __slots__ = (
        "detour_percent",
        "curve_preference",
        "hill_preference",
        "road_preference",
        "town_preference",
        "avoid_motorways",
    )

    def __init__(
        self,
        detour_percent=35.0,
        curve_preference=70.0,
        hill_preference=45.0,
        road_preference=75.0,
        town_preference=30.0,
        avoid_motorways=False,
    ):
        self.detour_percent = detour_percent
        self.curve_preference = curve_preference
        self.hill_preference = hill_preference
        self.road_preference = road_preference
        self.town_preference = town_preference
        self.avoid_motorways = avoid_motorways


class Label:
    # one path to a node
    __slots__ = ('node', 'eta', 'penalty', 'previous', 'edge_id', 'active')

    def __init__(self, node, eta, penalty, previous, edge_id, active=True):
        self.node = node
        self.eta = eta
        self.penalty = penalty
        self.previous = previous
        self.edge_id = edge_id
        self.active = active


class Route:
    __slots__ = (
        "edge_ids",
        "eta_minutes",
        "penalty",
        "distance_km",
        "twistiness",
        "hilliness",
        "elevation_gain_m",
        "major_road_percent",
        "town_road_percent",
        "coordinates",
    )

    def __init__(
        self,
        edge_ids,
        eta_minutes,
        penalty,
        distance_km=0,
        twistiness=0,
        hilliness=0,
        elevation_gain_m=0,
        major_road_percent=0,
        town_road_percent=0,
        coordinates=None,
    ):
        self.edge_ids = edge_ids
        self.eta_minutes = eta_minutes
        self.penalty = penalty
        self.distance_km = distance_km
        self.twistiness = twistiness
        self.hilliness = hilliness
        self.elevation_gain_m = elevation_gain_m
        self.major_road_percent = major_road_percent
        self.town_road_percent = town_road_percent
        self.coordinates = [] if coordinates is None else coordinates


class Router:
    def __init__(self, graph):
        self.graph = graph

    def _time_heuristic(self, node_id, target_id):
        node = self.graph.nodes[node_id]
        target = self.graph.nodes[target_id]
        distance = haversine_km(node.lat, node.lon, target.lat, target.lon)
        # optimistic remaining time
        return distance / self.graph.max_speed_kmh * 60

    def _can_use(self, edge, settings):
        return not (settings.avoid_motorways and edge.motorway)

    def edge_penalty(self, edge, settings):
        road = ROAD_PENALTIES.get(edge.road_class, 0.25)
        curve = max(0.0, min(1.0, edge.curve_score))
        hill = max(0.0, min(1.0, edge.hill_score))
        town = 1.0 if edge.road_class in TOWN_CLASSES else 0.0

        road_factor = 1 + (
            settings.road_preference / 100 * 3 * road
            + settings.town_preference / 100 * 2 * town
        )
        scenery_factor = 1 + (
            settings.curve_preference / 100 * 3 * curve
            + settings.hill_preference / 100 * 3 * hill
        )
        # lower penalty means a better match
        return edge.distance_km * road_factor / scenery_factor

    def fastest_path(self, start, target, settings):
        queue = []
        serial = count()  # breaks queue ties
        h_cache = {}

        def heuristic(node_id):
            if node_id not in h_cache:
                h_cache[node_id] = self._time_heuristic(node_id, target)
            return h_cache[node_id]

        heapq.heappush(queue, (heuristic(start), 0.0, next(serial), start))
        best = {start: 0.0}
        previous = {}
        expanded = 0

        while queue:
            _, current_eta, _, node = heapq.heappop(queue)
            # a faster path may have replaced this entry
            if current_eta != best.get(node):
                continue
            if node == target:
                edges = []
                while node != start:
                    old_node, edge_id = previous[node]
                    edges.append(edge_id)
                    node = old_node
                edges.reverse()
                return edges, current_eta, {"fastest_expanded": expanded}

            expanded += 1
            for edge_id in self.graph.adjacency.get(node, ()):
                edge = self.graph.edges[edge_id]
                if not self._can_use(edge, settings):
                    continue
                new_eta = current_eta + edge.eta_minutes
                if new_eta < best.get(edge.target, inf):
                    best[edge.target] = new_eta
                    previous[edge.target] = (node, edge.id)
                    estimate = new_eta + heuristic(edge.target)
                    heapq.heappush(queue, (estimate, new_eta, next(serial), edge.target))
        return None

    @staticmethod
    def _dominates(old, eta, penalty):
        # allow a 1.5% margin to shrink the search
        return (
            old.eta <= eta * (1 + DOMINANCE_MARGIN)
            and old.penalty <= penalty * (1 + DOMINANCE_MARGIN)
        )

    @staticmethod
    def _beats_old(eta, penalty, old):
        return eta <= old.eta and penalty <= old.penalty and (
            eta < old.eta or penalty < old.penalty
        )

    def _trim_labels(self, label_ids, labels):
        removed = 0
        while len(label_ids) > LABEL_LIMIT:
            ordered = sorted(label_ids, key=lambda item: labels[item].eta)
            lowest_penalty = min(ordered, key=lambda item: labels[item].penalty)
            # keep fastest and lowest penalty
            protected = {ordered[0], lowest_penalty}
            eta_span = max(labels[ordered[-1]].eta - labels[ordered[0]].eta, 1e-9)
            costs = [labels[item].penalty for item in ordered]
            cost_span = max(max(costs) - min(costs), 1e-9)

            remove_id = None
            smallest_gap = inf
            for index in range(1, len(ordered) - 1):
                label_id = ordered[index]
                if label_id in protected:
                    continue
                before = labels[ordered[index - 1]]
                after = labels[ordered[index + 1]]
                # remove crowded choices first
                gap = (after.eta - before.eta) / eta_span
                gap += abs(after.penalty - before.penalty) / cost_span
                if gap < smallest_gap:
                    smallest_gap = gap
                    remove_id = label_id

            if remove_id is None:
                for item in ordered:
                    if item not in protected:
                        remove_id = item
                        break
            labels[remove_id].active = False
            label_ids.remove(remove_id)
            removed += 1
        return removed

    def search(self, start, target, settings):
        started = perf_counter()
        fastest_result = self.fastest_path(start, target, settings)
        if fastest_result is None:
            reason = "no_path"
            if settings.avoid_motorways:
                relaxed = copy(settings)
                relaxed.avoid_motorways = False
                if self.fastest_path(start, target, relaxed) is not None:
                    reason = "motorway_filter"
            return [], {
                "reason": reason,
                "elapsed_ms": round((perf_counter() - started) * 1000, 2),
            }

        fastest_edges, fastest_eta, fastest_debug = fastest_result
        # detour limits travel time
        eta_limit = fastest_eta * (1 + settings.detour_percent / 100)
        fastest_penalty = sum(
            self.edge_penalty(self.graph.edges[item], settings)
            for item in fastest_edges
        )
        fastest_route = Route(fastest_edges, fastest_eta, fastest_penalty)
        active_preferences = (
            settings.curve_preference
            + settings.hill_preference
            + settings.road_preference
            + settings.town_preference
        )
        if active_preferences == 0:
            self._fill_statistics(fastest_route)
            return [fastest_route], {
                **fastest_debug,
                "fastest_eta": round(fastest_eta, 4),
                "eta_limit": round(eta_limit, 4),
                "labels_created": 0,
                "labels_expanded": 0,
                "dominance_removed": 0,
                "time_bound_removed": 0,
                "label_cap_removed": 0,
                "target_labels": 1,
                "peak_queue": 0,
                "elapsed_ms": round((perf_counter() - started) * 1000, 2),
            }
        h_cache = {}

        def heuristic(node_id):
            if node_id not in h_cache:
                h_cache[node_id] = self._time_heuristic(node_id, target)
            return h_cache[node_id]

        labels = [Label(start, 0.0, 0.0, None, None)]
        labels_here = {start: [0]}
        queue = [(heuristic(start), 0.0, 0, 0)]
        serial = count(1)
        expanded = 0
        dominance_removed = 0
        over_limit = 0
        cap_removed = 0
        peak_queue = 1

        while queue:
            _, _, _, label_id = heapq.heappop(queue)
            label = labels[label_id]
            if not label.active or label.node == target:
                continue

            finished = [
                labels[item]
                for item in labels_here.get(target, ())
                if labels[item].active
            ]
            # stop if a finished route is already better
            lower_eta = label.eta + heuristic(label.node)
            if any(
                item.eta <= lower_eta and item.penalty <= label.penalty
                for item in finished
            ):
                dominance_removed += 1
                continue

            expanded += 1
            for edge_id in self.graph.adjacency.get(label.node, ()):
                edge = self.graph.edges[edge_id]
                if not self._can_use(edge, settings):
                    continue
                eta = label.eta + edge.eta_minutes
                # even the optimistic time must fit
                if eta + heuristic(edge.target) > eta_limit + 1e-9:
                    over_limit += 1
                    continue
                penalty = label.penalty + self.edge_penalty(edge, settings)
                node_labels = labels_here.setdefault(edge.target, [])
                active = [labels[item] for item in node_labels if labels[item].active]
                if any(self._dominates(item, eta, penalty) for item in active):
                    dominance_removed += 1
                    continue

                for old_id in list(node_labels):
                    old = labels[old_id]
                    if old.active and self._beats_old(eta, penalty, old):
                        old.active = False
                        node_labels.remove(old_id)
                        dominance_removed += 1

                # keep parents for rebuilding paths
                new_id = len(labels)
                new_label = Label(edge.target, eta, penalty, label_id, edge.id)
                labels.append(new_label)
                node_labels.append(new_id)
                if edge.target != target:
                    cap_removed += self._trim_labels(node_labels, labels)
                if new_label.active:
                    estimate = eta + heuristic(edge.target)
                    heapq.heappush(
                        queue, (estimate, penalty, next(serial), new_id)
                    )
                    peak_queue = max(peak_queue, len(queue))

        target_ids = [
            item for item in labels_here.get(target, ()) if labels[item].active
        ]
        candidates = []
        for label_id in target_ids:
            label = labels[label_id]
            edge_ids = self._reconstruct_label(labels, label_id)
            candidates.append(Route(edge_ids, label.eta, label.penalty))
        candidates.append(fastest_route)
        candidates = self._deduplicate(candidates)
        for route in candidates:
            self._fill_statistics(route)

        selected = self._select_routes(candidates)
        debug = {
            **fastest_debug,
            "fastest_eta": round(fastest_eta, 4),
            "eta_limit": round(eta_limit, 4),
            "labels_created": len(labels),
            "labels_expanded": expanded,
            "dominance_removed": dominance_removed,
            "time_bound_removed": over_limit,
            "label_cap_removed": cap_removed,
            "target_labels": len(target_ids),
            "peak_queue": peak_queue,
            "elapsed_ms": round((perf_counter() - started) * 1000, 2),
        }
        return selected, debug

    @staticmethod
    def _reconstruct_label(labels, label_id):
        edges = []
        # walk back from the destination
        while labels[label_id].previous is not None:
            edge_id = labels[label_id].edge_id
            if edge_id is None:
                raise RuntimeError("broken route label")
            edges.append(edge_id)
            label_id = labels[label_id].previous
        edges.reverse()
        return edges

    @staticmethod
    def _deduplicate(routes):
        found = {}
        for route in routes:
            key = tuple(route.edge_ids)
            previous = found.get(key)
            if previous is None or route.eta_minutes < previous.eta_minutes:
                found[key] = route
        return list(found.values())

    def _fill_statistics(self, route):
        edges = [self.graph.edges[edge_id] for edge_id in route.edge_ids]
        route.distance_km = sum(edge.distance_km for edge in edges)
        route.eta_minutes = sum(edge.eta_minutes for edge in edges)
        if route.distance_km:
            # weight scores by road length
            route.twistiness = (
                sum(edge.curve_score * edge.distance_km for edge in edges)
                / route.distance_km * 100
            )
            route.hilliness = (
                sum(edge.hill_score * edge.distance_km for edge in edges)
                / route.distance_km * 100
            )
            route.elevation_gain_m = sum(
                max(0.0, edge.elevation_change_m) for edge in edges
            )
            major = sum(
                edge.distance_km for edge in edges
                if edge.road_class in MAJOR_CLASSES
            )
            route.major_road_percent = major / route.distance_km * 100
            town = sum(
                edge.distance_km for edge in edges
                if edge.road_class in TOWN_CLASSES
            )
            route.town_road_percent = town / route.distance_km * 100
        route.coordinates = self.route_coordinates(route.edge_ids)

    def route_coordinates(self, edge_ids):
        coordinates = []
        for edge_id in edge_ids:
            geometry = list(self.graph.edges[edge_id].geometry)
            if not coordinates:
                coordinates.extend(geometry)
            elif coordinates[-1] == geometry[0]:
                coordinates.extend(geometry[1:])  # skip shared endpoint
            else:
                raise ValueError(f"Route is not continuous at edge {edge_id}")
        return coordinates

    def route_overlap(self, first, second):
        first_roads = {}
        second_roads = {}
        # count both directions as one road
        for edge_id in first.edge_ids:
            edge = self.graph.edges[edge_id]
            first_roads.setdefault(edge.physical_id, edge.distance_km)
        for edge_id in second.edge_ids:
            edge = self.graph.edges[edge_id]
            second_roads.setdefault(edge.physical_id, edge.distance_km)
        shared = sum(
            first_roads[item] for item in first_roads.keys() & second_roads.keys()
        )
        shorter = min(first.distance_km, second.distance_km)
        return shared / shorter * 100 if shorter else 0.0

    def route_separation(self, first, second):
        def sample(points):
            # sample points to keep this quick
            step = max(1, len(points) // 70)
            picked = points[::step]
            if picked[-1] != points[-1]:
                picked.append(points[-1])
            return picked

        first_points = sample(first.coordinates)
        second_points = sample(second.coordinates)

        def furthest(points, other):
            greatest_distance = 0.0
            for lat, lon in points:
                nearest = min(
                    haversine_km(lat, lon, lat2, lon2)
                    for lat2, lon2 in other
                )
                greatest_distance = max(greatest_distance, nearest)
            return greatest_distance

        return max(
            furthest(first_points, second_points),
            furthest(second_points, first_points),
        )

    def meaningfully_different(self, first, second):
        return (
            self.route_overlap(first, second) <= 60
            and self.route_separation(first, second) >= 0.4
        )

    def _select_routes(self, candidates):
        if not candidates:
            return []
        fastest = min(candidates, key=lambda route: route.eta_minutes)
        # compare penalty per km
        fastest_quality = fastest.penalty / fastest.distance_km
        options = []
        for route in candidates:
            quality = route.penalty / route.distance_km
            if route is fastest or quality >= fastest_quality:
                continue
            if self.meaningfully_different(route, fastest):
                options.append(route)

        options.sort(key=lambda route: route.eta_minutes)
        compatible = []
        for first in options:
            row = []
            for second in options:
                row.append(self.meaningfully_different(first, second))
            compatible.append(row)
        best = []

        # try keeping and skipping each alternative
        def pick(index, chosen):
            nonlocal best
            # this branch cannot beat the best set
            if len(chosen) + len(options) - index <= len(best):
                return
            if index == len(options):
                best = chosen.copy()
                return
            if all(compatible[index][old] for old in chosen):
                chosen.append(index)
                pick(index + 1, chosen)
                chosen.pop()
            pick(index + 1, chosen)

        pick(0, [])
        selected = [fastest] + [options[index] for index in best]
        selected.sort(key=lambda route: route.eta_minutes)

        return selected
