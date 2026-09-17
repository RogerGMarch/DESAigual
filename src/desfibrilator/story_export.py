"""Export audited, aggregate public data for the CardioResilient prototype.

The source DuckDB is read-only. Suspect legacy crosswalks are excluded from
coverage rather than silently relabeled. Exact duplicate building rows are
collapsed before joining; conflicting keys are rejected at municipality level.
"""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import duckdb

from desfibrilator.crosswalk import name_key, resolve_municipality
from desfibrilator.normalize import address_key


def feature(coordinates, properties):
    """Make a GeoJSON point using rounded WGS84 coordinates."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [round(v, 5) for v in coordinates],
        },
        "properties": properties,
    }


def footprint_features(buildings, access):
    """Join audited León access by cadastral building ID, preserving polygons."""
    if buildings.crs is None:
        raise ValueError("Cadastral footprints require a declared CRS")
    frame = buildings.copy()
    frame["building_id"] = "24089:" + frame["localId"].astype(str)
    frame = frame[frame["building_id"].isin(access)].copy()
    frame["geometry"] = frame.geometry.make_valid()
    frame = frame[frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    frame["_shape"] = frame.geometry.normalize().to_wkb()
    frame = frame.drop_duplicates(["building_id", "_shape"])
    if frame["building_id"].duplicated().any():
        raise ValueError("Conflicting cadastral footprints for a building ID")
    frame["minutes"] = frame["building_id"].map(access)
    frame = frame.sort_values("building_id").to_crs("EPSG:4326")
    return json.loads(frame[["building_id", "minutes", "geometry"]].to_json())[
        "features"
    ]


def export_story(database: Path, output: Path, footprint_root: Path) -> dict:
    """Export municipality metrics and map layers with a machine-readable audit."""
    connection = duckdb.connect(str(database), read_only=True)
    municipalities = connection.execute(
        """SELECT cod_ine, municipio, cod_provincia, poblacion, longitude, latitude
           FROM municipalities ORDER BY cod_ine"""
    ).fetchall()
    by_name = {
        (name_key(name), str(province).zfill(2)): (ine, name, population)
        for ine, name, province, population, *_ in municipalities
    }
    official_ids = {row[0] for row in municipalities}
    with (footprint_root.parent / "manifest.csv").open(encoding="utf-8") as file:
        names = {
            row["municipality_id"]: (row["municipality_name"], row["province_code"])
            for row in csv.DictReader(file)
        }
    suspect = set()
    assignments = Counter()
    for path in sorted(footprint_root.glob("*/*.building.gml")):
        cadastral_id = path.parent.name
        match = resolve_municipality(cadastral_id, names, by_name)
        if match is None and cadastral_id in official_ids:
            # The previous importer could place this file into a different town.
            suspect.add(cadastral_id)
        elif match is not None:
            assignments[match[0]] += 1
    suspect.update(ine for ine, count in assignments.items() if count > 1)
    # Replacement OSM/point rows do not use the legacy cadastral crosswalk.
    sources = dict(
        connection.execute("""
        SELECT municipality_id, string_agg(DISTINCT coalesce(building_source,
            'cadastre'), ',' ORDER BY coalesce(building_source, 'cadastre'))
        FROM building_population GROUP BY municipality_id
    """).fetchall()
    )
    suspect.difference_update(
        ine
        for ine, source in sources.items()
        if set(source.split(",")) <= {"osm_fallback", "nominatim_point"}
    )
    # TEMP tables live only in this connection, never in the source database.
    connection.execute("""
        CREATE TEMP TABLE clean_population AS
        SELECT DISTINCT building_id, municipality_id, x, y, estimated_population
        FROM building_population;
        CREATE TEMP TABLE clean_access AS
        SELECT DISTINCT building_id, municipality_id, walk_time_minutes,
                        access_5_minutes, access_10_minutes, access_15_minutes
        FROM building_aed_access;
    """)
    for table in ("clean_population", "clean_access"):
        suspect.update(
            row[0]
            for row in connection.execute(f"""
            SELECT DISTINCT municipality_id FROM (
                SELECT municipality_id, building_id FROM {table}
                GROUP BY ALL HAVING count(*) > 1
            )
        """).fetchall()
        )
    results = connection.execute("""
        SELECT p.municipality_id, sum(p.estimated_population),
               sum(CASE WHEN a.access_5_minutes THEN p.estimated_population ELSE 0 END),
               sum(CASE WHEN a.access_10_minutes
                        THEN p.estimated_population ELSE 0 END),
               sum(CASE WHEN a.access_15_minutes
                        THEN p.estimated_population ELSE 0 END),
               count(*), count(a.building_id)
        FROM clean_population p LEFT JOIN clean_access a
        USING (building_id, municipality_id) GROUP BY p.municipality_id
    """).fetchall()
    access = {}
    for ine, total, p5, p10, p15, count, matched in results:
        if ine in suspect or total <= 0 or count != matched:
            continue
        fractions = [p5 / total, p10 / total, p15 / total]
        if not (0 <= fractions[0] <= fractions[1] <= fractions[2] <= 1.00000001):
            raise ValueError(f"Invalid coverage fractions for {ine}")
        access[ine] = {
            "coverage": [round(f * 100, 2) for f in fractions],
            "buildings": count,
        }
    geocodes = {
        key: (lon, lat, precision, provider)
        for key, lon, lat, precision, provider in connection.execute("""
            SELECT address_key, longitude, latitude, match_precision, provider
            FROM aed_geocodes WHERE match_status LIKE 'accepted%'
            AND longitude IS NOT NULL AND latitude IS NOT NULL
        """).fetchall()
    }
    aeds = []
    source = connection.execute("""
        SELECT aed_id, address, municipality, province FROM aed_locations
        ORDER BY aed_id, address, municipality, province
    """).fetchall()
    for index, (aed_id, address, municipality, province) in enumerate(source):
        coordinate = geocodes.get(address_key(address, municipality, province))
        if coordinate is None:
            continue
        lon, lat, precision, provider = coordinate
        aeds.append(
            feature(
                [lon, lat],
                {
                    "id": str(index),
                    "registryId": aed_id,
                    "precision": precision or "unknown",
                    "provider": provider,
                },
            )
        )
    municipal_features = []
    population_covered = 0
    covered = [0, 0, 0]
    for ine, name, province, population, lon, lat in municipalities:
        metrics = access.get(ine)
        properties = {
            "id": ine,
            "name": name,
            "province": province,
            "population": population,
            "populationSource": sources.get(ine),
            "status": "review"
            if ine in suspect
            else ("available" if metrics else "missing"),
        }
        if metrics and ine not in suspect:
            properties.update(metrics)
            for threshold, value in zip((5, 10, 15), metrics["coverage"], strict=True):
                properties[f"coverage{threshold}"] = value
            population_covered += population
            for index, fraction in enumerate(metrics["coverage"]):
                covered[index] += population * fraction / 100
        if lon is not None and lat is not None:
            municipal_features.append(feature([lon, lat], properties))
    # León is deliberately a detailed case, not a sample passed off as the region.
    leon = []
    if "24089" not in suspect:
        leon_access = dict(
            connection.execute("""
            SELECT p.building_id, a.walk_time_minutes FROM clean_population p
            JOIN clean_access a USING (building_id, municipality_id)
            WHERE p.municipality_id = '24089' ORDER BY p.building_id
        """).fetchall()
        )
        if leon_access:
            import geopandas as gpd

            for path in sorted(footprint_root.glob("*/*.building.gml")):
                match = resolve_municipality(path.parent.name, names, by_name)
                if match is not None and match[0] == "24089":
                    leon.extend(footprint_features(gpd.read_file(path), leon_access))
    from desfibrilator.city_story import export_city_footprints

    export_city_footprints(
        connection, database.parent / "city_buildings", output, access
    )
    # Geometry comes from the actual OSM graph; simplify connected major roads.
    from shapely import from_wkt
    from shapely.geometry import mapping
    from shapely.ops import linemerge, unary_union

    road_wkts = connection.execute("""
        SELECT DISTINCT geometry_wkt FROM road_edges
        WHERE highway IN ('motorway', 'trunk', 'primary')
        AND geometry_wkt IS NOT NULL
    """).fetchall()
    roads = linemerge(unary_union([from_wkt(row[0]) for row in road_wkts]))
    roads = mapping(roads.simplify(0.001, preserve_topology=False))
    summary = {
        "sourceDate": "2026-09-07",
        "exportVersion": 2,
        "populationSources": dict(Counter(sources.values())),
        "municipalities": len(municipalities),
        "registryRecords": len(source),
        "mappedRecords": len(aeds),
        "population": sum(row[3] for row in municipalities),
        "municipalitiesWithAccess": len(access),
        "reviewMunicipalities": sorted(suspect),
        "modeledPopulation": population_covered,
        "coverage": [round(value / population_covered * 100, 1) for value in covered],
        "method": "Unique building rows; exclude suspect legacy crosswalks; "
        "weight municipal coverage fractions by official population.",
        "walkingSpeedKmh": 4.8,
        "searchLimitMinutes": 360,
        "nullMeaning": "No route found within the 360-minute search and 500 m snapping limits; "
        "not an observed journey time or proof of disconnection.",
        "sourceDatabaseModified": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, value in (
        ("summary.json", summary),
        (
            "municipalities.geojson",
            {"type": "FeatureCollection", "features": municipal_features},
        ),
        ("aeds.geojson", {"type": "FeatureCollection", "features": aeds}),
        ("leon.geojson", {"type": "FeatureCollection", "features": leon}),
        ("roads.geojson", {"type": "Feature", "geometry": roads, "properties": {}}),
    ):
        (output / filename).write_text(
            json.dumps(
                value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ),
            encoding="utf-8",
        )
    if connection.execute("SELECT count(*) FROM node_hospital_access").fetchone()[0]:
        from desfibrilator.hospital_story import export_hospital_surface

        export_hospital_surface(
            connection,
            output,
            boundary_path=footprint_root.parents[2]
            / "interim"
            / "castilla_y_leon_boundary.gpkg",
        )
    connection.close()
    return summary


def main():
    """Read CLI paths and export the self-contained map layers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument("--output", type=Path, default=Path("web/public/data"))
    parser.add_argument(
        "--footprints",
        type=Path,
        default=Path("data/raw/catastro_buildings/footprints"),
    )
    args = parser.parse_args()
    print(
        json.dumps(export_story(args.database, args.output, args.footprints), indent=2)
    )


if __name__ == "__main__":
    main()
