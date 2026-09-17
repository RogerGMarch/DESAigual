import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from desfibrilator.city_story import city_features


def test_city_join_uses_current_times_and_preserves_holes_and_nulls():
    polygon = Polygon(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        [[(2, 2), (2, 4), (4, 4), (4, 2)]],
    )
    frame = gpd.GeoDataFrame(
        {
            "building_id": ["49275:OSM-a", "49275:OSM-a", "49275:OSM-b", "other"],
            "walk_time_minutes": [99, 99, 99, 99],
        },
        geometry=[polygon] * 4,
        crs=25830,
    )
    features = city_features(frame, {"49275:OSM-a": 3, "49275:OSM-b": None})["features"]
    assert len(features) == 2
    assert [f["properties"]["minutes"] for f in features] == [3, None]
    assert len(features[0]["geometry"]["coordinates"]) == 2
    frame.loc[1, "geometry"] = polygon.buffer(1)
    with pytest.raises(ValueError, match="Conflicting"):
        city_features(frame, {"49275:OSM-a": 3})
