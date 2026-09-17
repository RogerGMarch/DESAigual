"""Export city polygons on demand, joined to the current audited database."""

import json
from pathlib import Path

import geopandas as gpd


def city_features(frame, access):
    """Keep unique residential polygons, their holes and current access values."""
    if frame.crs is None:
        raise ValueError("City footprints require a CRS")
    frame = frame[frame.building_id.isin(access)].copy()
    frame.geometry = frame.geometry.make_valid()
    frame = frame[frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    frame["_shape"] = frame.geometry.normalize().to_wkb()
    frame = frame.drop_duplicates(["building_id", "_shape"])
    if frame.building_id.duplicated().any():
        raise ValueError("Conflicting city footprints for a building ID")
    frame["minutes"] = frame.building_id.map(access)
    frame = frame.sort_values("building_id").to_crs(4326)
    return json.loads(frame[["building_id", "minutes", "geometry"]].to_json())


def export_city_footprints(connection, source: Path, output: Path, audited):
    """Publish separate city files and provenance without using stale GPKG times."""
    municipalities = dict(
        connection.execute("SELECT cod_ine, municipio FROM municipalities").fetchall()
    )
    cities = {}
    target = output / "cities"
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob("*_building_aed_access.gpkg")):
        frame = gpd.read_file(path, columns=["building_id"])
        ids = set(frame.building_id.str.split(":").str[0])
        if len(ids) != 1:
            raise ValueError(f"Mixed municipality IDs in {path}")
        ine = ids.pop()
        if ine not in audited:
            continue
        access = dict(
            connection.execute(
                """
            SELECT p.building_id, a.walk_time_minutes FROM clean_population p
            JOIN clean_access a USING (building_id, municipality_id)
            WHERE p.municipality_id = ? ORDER BY p.building_id
        """,
                [ine],
            ).fetchall()
        )
        layer = city_features(frame, access)
        if not layer["features"]:
            continue
        points = frame[frame.building_id.isin(access)].geometry.centroid.to_crs(4326)
        center = [float(points.x.median()), float(points.y.median())]
        osm = frame.building_id.str.contains(":OSM-").any()
        filename = f"cities/{ine}.geojson"
        (output / filename).write_text(
            json.dumps(
                layer, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            )
        )
        cities[ine] = {
            "name": municipalities[ine],
            "center": center,
            "file": filename,
            "buildings": len(layer["features"]),
            "source": "OpenStreetMap" if osm else "Catastro INSPIRE",
            "sourceFile": path.name,
        }
    (output / "cities.json").write_text(
        json.dumps(cities, ensure_ascii=False, indent=2)
    )
    return cities
