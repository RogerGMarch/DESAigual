import hashlib
import json

import duckdb

from desfibrilator.schema import create_schema
from desfibrilator.story_export import export_story


def test_export_deduplicates_and_quarantines_legacy_crosswalk(tmp_path):
    database = tmp_path / "source.duckdb"
    connection = duckdb.connect(str(database))
    create_schema(connection)
    connection.execute("""
        INSERT INTO municipalities
            (cod_ine, municipio, cod_provincia, poblacion, longitude, latitude)
        VALUES ('00001', 'ALPHA', '00', 100, 0, 41),
               ('00002', 'BETA', '00', 200, 1, 41);
        INSERT INTO building_population
            (building_id, municipality_id, x, y, estimated_population)
        VALUES ('a', '00001', 0, 0, 50), ('a', '00001', 0, 0, 50),
               ('b', '00001', 1, 1, 50), ('c', '00002', 2, 2, 200);
        INSERT INTO building_aed_access
            (building_id, municipality_id, walk_time_minutes,
             access_5_minutes, access_10_minutes, access_15_minutes)
        VALUES ('a', '00001', 3, true, true, true),
               ('a', '00001', 3, true, true, true),
               ('b', '00001', NULL, false, false, false),
               ('c', '00002', 2, true, true, true);
        INSERT INTO road_edges (highway, geometry_wkt)
        VALUES ('primary', 'LINESTRING (0 0, 1 0)'),
               ('primary', 'LINESTRING (1 0, 2 0)');
    """)
    connection.close()
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    footprints = tmp_path / "footprints"
    for code in ("00001", "00002"):
        (footprints / code).mkdir(parents=True)
        (footprints / code / "sample.building.gml").touch()
    (tmp_path / "manifest.csv").write_text(
        "municipality_id,municipality_name,province_code\n"
        "00001,ALPHA,00\n00002,A DIFFERENT TOWN,00\n"
    )
    summary = export_story(database, tmp_path / "output", footprints)
    features = json.loads((tmp_path / "output" / "municipalities.geojson").read_text())[
        "features"
    ]
    assert summary["coverage"] == [50.0, 50.0, 50.0]
    assert summary["modeledPopulation"] == 100
    assert summary["municipalitiesWithAccess"] == 1
    assert features[0]["properties"]["buildings"] == 2
    assert features[1]["properties"]["status"] == "review"
    assert "coverage15" not in features[1]["properties"]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before

    # A replacement source must not inherit an obsolete cadastral exclusion.
    connection = duckdb.connect(str(database))
    connection.execute(
        "UPDATE building_population SET building_source = 'osm_fallback' WHERE municipality_id = '00002'"
    )
    connection.close()
    summary = export_story(database, tmp_path / "output", footprints)
    assert summary["municipalitiesWithAccess"] == 2
    assert summary["modeledPopulation"] == 300
    assert summary["reviewMunicipalities"] == []


def test_footprints_join_by_id_and_preserve_holes():
    import geopandas as gpd
    from shapely.geometry import Polygon

    from desfibrilator.story_export import footprint_features

    polygon = Polygon(
        [(0, 0), (10, 0), (10, 10), (0, 10)],
        [[(2, 2), (2, 4), (4, 4), (4, 2)]],
    )
    frame = gpd.GeoDataFrame(
        {"localId": ["a", "a", "b"]},
        geometry=[polygon, polygon, polygon],
        crs="EPSG:25830",
    )
    result = footprint_features(frame, {"24089:a": None})
    assert len(result) == 1
    assert result[0]["properties"] == {"building_id": "24089:a", "minutes": None}
    assert result[0]["geometry"]["type"] == "Polygon"
    assert len(result[0]["geometry"]["coordinates"]) == 2
