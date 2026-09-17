import pandas as pd

from desfibrilator.network import (
    is_oneway,
    parse_speed_kmh,
    prepare_directed_edges,
    travel_time_minutes,
)


def test_parse_speed_supports_mph_and_highway_defaults():
    assert parse_speed_kmh("30 mph") == 48.28032
    assert parse_speed_kmh(None, "residential") == 30


def test_travel_time_is_calculated_in_minutes():
    assert travel_time_minutes(1000, 60) == 1.0


def test_prepare_directed_edges_expands_two_way_and_respects_oneway():
    edges = pd.DataFrame(
        [
            {
                "id": 1,
                "u": 10,
                "v": 20,
                "length": 100,
                "highway": "primary",
                "oneway": "no",
            },
            {
                "id": 2,
                "u": 20,
                "v": 30,
                "length": 100,
                "highway": "primary",
                "oneway": "yes",
            },
        ]
    )

    prepared = prepare_directed_edges(edges)

    assert [(row[1], row[2]) for row in prepared] == [(10, 20), (20, 10), (20, 30)]
    assert is_oneway("-1") == "reverse"
