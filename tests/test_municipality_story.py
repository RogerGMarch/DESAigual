import pytest

from desfibrilator.municipality_story import analyze


def test_size_distribution_keeps_missing_and_access_is_population_weighted():
    rows = [
        {"population": 100, "status": "available", "coverage5": 0},
        {"population": 300, "status": "available", "coverage5": 100},
        {"population": 499, "status": "missing"},
        {"population": 500, "status": "review"},
    ]
    result = analyze([{"properties": row} for row in rows])
    band = result["groups"][1]
    assert result["population"] == 1399
    assert band["municipalities"] == 3
    assert band["population"] == 899
    assert band["coverage5"] == 75
    assert band["modeledPopulationShare"] == pytest.approx(400 / 899 * 100)
    assert result["groups"][2]["coverage5"] is None
    assert sum(g["populationShare"] for g in result["groups"]) == pytest.approx(100)
