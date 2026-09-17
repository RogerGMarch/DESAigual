import geopandas as gpd
import pytest
from shapely.geometry import box

from desfibrilator.buildings import allocate_population_to_buildings


def test_duplicate_footprint_does_not_receive_population_twice():
    frame = gpd.GeoDataFrame(
        {"localId": ["a", "a", "b"], "currentUse": ["1_residential"] * 3},
        geometry=[box(0, 0, 10, 10), box(0, 0, 10, 10), box(20, 0, 30, 10)],
        crs="EPSG:25830",
    )
    result = allocate_population_to_buildings(frame, "00001", "Example", 100)
    assert len(result) == 2
    assert result.estimated_population.tolist() == pytest.approx([50, 50])


def test_conflicting_building_ids_are_rejected_instead_of_arbitrarily_joined():
    frame = gpd.GeoDataFrame(
        {"localId": ["a", "a"], "currentUse": ["1_residential"] * 2},
        geometry=[box(0, 0, 10, 10), box(20, 0, 30, 10)],
        crs="EPSG:25830",
    )
    with pytest.raises(ValueError, match="Conflicting duplicate building IDs"):
        allocate_population_to_buildings(frame, "00001", "Example", 100)
