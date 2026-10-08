import pytest

from route_planner.osm_import import (
    legal_speed,
    parse_speed,
    road_speed,
    segment_curve,
)


def test_speed_parser():
    assert parse_speed("90") == 90
    assert parse_speed("50 mph") == pytest.approx(80.4672)
    assert parse_speed("CZ:urban") == 50
    assert parse_speed("150") == 150
    assert parse_speed("signals") is None


def test_czech_legal_speed_fallbacks():
    assert legal_speed({}, "motorway") == 130
    assert legal_speed({}, "trunk") == 110
    assert legal_speed({}, "secondary") == 90
    assert legal_speed({}, "residential") == 50
    assert legal_speed({}, "living_street") == 20
    assert legal_speed({"source:maxspeed": "CZ:urban"}, "primary") == 50
    assert legal_speed({"motorroad": "no"}, "trunk") == 90


def test_eta_speed_is_separate_and_never_exceeds_limit():
    assert road_speed({}, "motorway") == 90
    assert road_speed({"maxspeed": "50"}, "primary") == 50
    assert road_speed({"maxspeed": "90"}, "primary") == 65


def test_curve_score_distinguishes_bend():
    straight = [(49.0, 15.0), (49.0, 15.01), (49.0, 15.02)]
    bent = [(49.0, 15.0), (49.0, 15.01), (49.01, 15.01)]
    assert segment_curve(straight, 0, 0.7) == 0
    assert segment_curve(bent, 0, 0.7) > 0.5
