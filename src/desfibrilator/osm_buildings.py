"""Prepare OSM building footprints when cadastral data is unavailable."""

import argparse
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
from pyrosm import OSM

from desfibrilator.buildings import allocate_population_to_buildings
from desfibrilator.schema import create_schema

RESIDENTIAL_BUILDING_TYPES = {
    "apartments",
    "bungalow",
    "cabin",
    "detached",
    "dormitory",
    "farm",
    "house",
    "residential",
    "semidetached_house",
    "terrace",
}


def prepare_zamora_osm_buildings(
    connection: duckdb.DuckDBPyConnection,
    pbf_path: Path,
    output_path: Path,
) -> dict[str, int | float]:
    """Extract, clip, and population-weight OSM buildings for Zamora."""
    if not pbf_path.exists():
        raise FileNotFoundError(pbf_path)
    osm = OSM(str(pbf_path), engine="out_of_core", workers=1)
    boundaries = osm.get_boundaries(name="Zamora")
    boundaries = boundaries[boundaries["admin_level"].astype(str) == "8"]
    if boundaries.empty:
        raise ValueError("Zamora municipal boundary was not found in OSM")
    boundary = boundaries.geometry.iloc[0]
    buildings = OSM(
        str(pbf_path), engine="out_of_core", workers=1, bounding_box=boundary
    ).get_buildings()
    buildings = gpd.clip(buildings, boundaries[["geometry"]])
    buildings = buildings[buildings.geometry.notna() & ~buildings.geometry.is_empty]
    buildings["localId"] = [f"OSM-{value}" for value in buildings["id"].astype(str)]
    if "building" in buildings.columns:
        residential = buildings[
            buildings["building"].fillna("").isin(RESIDENTIAL_BUILDING_TYPES)
        ].copy()
    else:
        residential = buildings.copy()
    population = connection.sql(
        "SELECT poblacion FROM municipalities WHERE cod_ine = '49275'"
    ).fetchone()
    if population is None:
        raise ValueError("Official Zamora population is not available")
    result = allocate_population_to_buildings(
        residential,
        "49275",
        "ZAMORA",
        float(population[0] or 0),
    )
    if result.empty:
        raise ValueError("No residential OSM buildings found for Zamora")
    create_schema(connection)
    connection.execute(
        "DELETE FROM building_population WHERE municipality_id = '49275'"
    )
    frame = pd.DataFrame(result.drop(columns="geometry"))
    connection.register("_zamora_buildings", frame)
    try:
        connection.execute(
            """
            INSERT INTO building_population
                (building_id, municipality_id, x, y, estimated_population,
                 residential_use)
            SELECT building_id, municipality_id, x, y, estimated_population,
                   'osm_residential'
            FROM _zamora_buildings
            """
        )
    finally:
        connection.unregister("_zamora_buildings")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_columns = [
        column
        for column in ("id", "localId", "name", "building", "geometry")
        if column in buildings
    ]
    buildings[output_columns].to_file(
        output_path, layer="zamora_osm_buildings", driver="GPKG"
    )
    return {
        "osm_buildings": len(buildings),
        "residential_buildings": len(result),
        "population": float(result["estimated_population"].sum()),
    }


def main() -> None:
    """Prepare the Zamora OSM fallback building layer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--pbf", type=Path, default=Path("data/raw/castilla-y-leon-latest.osm.pbf")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/interim/osm_zamora_buildings.gpkg")
    )
    args = parser.parse_args()
    with duckdb.connect(str(args.database)) as connection:
        stats = prepare_zamora_osm_buildings(connection, args.pbf, args.output)
    print(stats)


if __name__ == "__main__":
    main()
