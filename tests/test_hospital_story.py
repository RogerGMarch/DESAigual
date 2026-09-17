import json

import duckdb
import matplotlib.image as mpimg

from desfibrilator.hospital_story import export_hospital_surface


def test_surface_uses_nearest_reachable_node_and_stays_north_up(tmp_path):
    connection = duckdb.connect()
    connection.execute("""
        CREATE TABLE road_nodes(node_id INTEGER, longitude DOUBLE, latitude DOUBLE);
        INSERT INTO road_nodes VALUES (1, -5, 42), (2, -5, 42.02);
        CREATE TABLE node_hospital_access(node_id INTEGER,
            network_time_minutes DOUBLE, access_status VARCHAR);
        INSERT INTO node_hospital_access VALUES
            (1, 20, 'reachable'), (2, NULL, 'unreachable');
        CREATE TABLE municipalities(longitude DOUBLE, latitude DOUBLE);
        INSERT INTO municipalities VALUES (-5.001, 42), (-4.999, 42.02);
        CREATE TABLE hospitals(hospital_id VARCHAR, name VARCHAR, longitude DOUBLE,
            latitude DOUBLE, emergency_capable BOOLEAN);
        INSERT INTO hospitals VALUES ('a', 'Hospital', -5, 42, true);
    """)
    result = export_hospital_surface(connection, tmp_path, grid_size=20)
    pixels = mpimg.imread(tmp_path / "hospital-times.png")
    assert pixels[0, 10, 3] == 1
    assert result["reachableRoadNodes"] == 1
    assert pixels[-1, 10, 3] == 1
    assert result["coordinates"][0][1] > result["coordinates"][3][1]
    assert result["maximum"] == 20
    assert (
        len(
            json.loads((tmp_path / "hospital-times.json").read_text())["hospitals"][
                "features"
            ]
        )
        == 1
    )


def test_surface_masks_region_and_keeps_expanded_times(tmp_path):
    import geopandas as gpd
    from shapely.geometry import Polygon

    connection = duckdb.connect()
    connection.execute("""
        CREATE TABLE road_nodes(node_id INTEGER, longitude DOUBLE, latitude DOUBLE);
        INSERT INTO road_nodes VALUES (1, -5, 42);
        CREATE TABLE node_hospital_access(node_id INTEGER,
            network_time_minutes DOUBLE, access_status VARCHAR);
        INSERT INTO node_hospital_access VALUES (1, 240, 'reachable');
        CREATE TABLE municipalities(longitude DOUBLE, latitude DOUBLE);
        INSERT INTO municipalities VALUES (-5.001, 42), (-4.999, 42.02);
        CREATE TABLE hospitals(hospital_id VARCHAR, name VARCHAR, longitude DOUBLE,
            latitude DOUBLE, emergency_capable BOOLEAN);
    """)
    boundary = tmp_path / "boundary.geojson"
    gpd.GeoDataFrame(
        geometry=[Polygon([(-5.01, 41.99), (-4.99, 41.99), (-5.01, 42.01)])], crs=4326
    ).to_file(boundary)
    result = export_hospital_surface(connection, tmp_path, 20, boundary)
    pixels = mpimg.imread(tmp_path / "hospital-times.png")
    assert pixels[0, -1, 3] == 0
    assert pixels[-1, 0, 3] == 1
    assert result["maximum"] == 240
    assert result["clippedToRegion"] is True
