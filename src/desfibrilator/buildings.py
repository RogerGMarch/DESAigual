"""Allocate municipality population to cadastral residential buildings."""

import argparse
import csv
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
from tobler.area_weighted import area_interpolate
from tqdm import tqdm

from desfibrilator.crosswalk import name_key, resolve_municipality
from desfibrilator.schema import create_schema

TARGET_CRS = "EPSG:25830"


def allocate_population_to_buildings(
    buildings: gpd.GeoDataFrame,
    municipality_id: str,
    municipality_name: str,
    population: float,
) -> gpd.GeoDataFrame:
    """Estimate resident population on residential cadastral footprints.

    Tobler's area-weighted interpolation allocates the municipality total over
    the residential building footprints. The output geometry is the building
    centroid in EPSG:25830, suitable for network snapping.
    """
    if buildings.crs is None:
        raise ValueError(f"Building layer has no CRS: {municipality_id}")
    buildings = buildings.to_crs(TARGET_CRS)
    buildings = buildings[buildings.geometry.notna() & ~buildings.geometry.is_empty]
    if "currentUse" in buildings.columns:
        residential = buildings[
            buildings["currentUse"].fillna("").astype(str).str.startswith("1_")
        ].copy()
    else:
        residential = buildings.copy()
    if residential.empty:
        return gpd.GeoDataFrame(columns=_output_columns(), crs=TARGET_CRS)
    residential["geometry"] = residential.geometry.make_valid()
    residential = residential[
        residential.geometry.notna() & ~residential.geometry.is_empty
    ].copy()
    residential["building_id"] = [
        f"{municipality_id}:{value}"
        for value in residential.get("localId", residential.index).astype(str)
    ]
    # Repeated downloads can contain identical footprint records. Keep each
    # building once before allocating population; reject conflicting identities.
    residential["_geometry_key"] = residential.geometry.normalize().to_wkb()
    residential = residential.drop_duplicates(["building_id", "_geometry_key"])
    if residential["building_id"].duplicated().any():
        raise ValueError(f"Conflicting duplicate building IDs: {municipality_id}")
    source_geometry = residential.geometry.union_all()
    source = gpd.GeoDataFrame(
        {"municipality_population": [float(population)]},
        geometry=[source_geometry],
        crs=TARGET_CRS,
    )
    target = residential[["building_id", "geometry"]].reset_index(drop=True)
    interpolated = area_interpolate(
        source,
        target,
        extensive_variables=["municipality_population"],
        allocate_total=True,
        n_jobs=1,
    )
    centroids = interpolated.geometry.centroid
    return gpd.GeoDataFrame(
        {
            "building_id": target["building_id"].to_numpy(),
            "municipality_id": municipality_id,
            "municipality_name": municipality_name,
            "x": centroids.x.to_numpy(),
            "y": centroids.y.to_numpy(),
            "estimated_population": interpolated["municipality_population"].to_numpy(
                float
            ),
        },
        geometry=centroids,
        crs=TARGET_CRS,
    )


def prepare_building_population(
    connection: duckdb.DuckDBPyConnection,
    footprint_root: Path,
    audit_path: Path | None = None,
) -> dict[str, float]:
    """Read cadastral files and persist building-level population estimates."""
    create_schema(connection)
    names = {}
    manifest_path = footprint_root.parent / "manifest.csv"
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                names[row["municipality_id"]] = (
                    row["municipality_name"],
                    row["province_code"],
                )
    by_name = {
        (_name_key(name), str(province).zfill(2)): (ine, name, float(population or 0))
        for name, province, ine, population in connection.sql(
            "SELECT municipio, cod_provincia, cod_ine, poblacion FROM municipalities"
        ).fetchall()
    }
    files = sorted(footprint_root.glob("*/*.building.gml"))
    if not files:
        raise FileNotFoundError(f"No cadastral footprints found below {footprint_root}")
    connection.execute("DELETE FROM building_population")
    audit = []
    totals = {"files": 0, "valid_files": 0, "skipped_files": 0, "buildings": 0}
    for path in tqdm(files, desc="Allocating building population", unit="file"):
        totals["files"] += 1
        municipality_id = path.parent.name
        metadata = resolve_municipality(municipality_id, names, by_name)
        if metadata is None:
            totals["skipped_files"] += 1
            audit.append(
                {
                    "municipality_id": municipality_id,
                    "status": "unmatched_crosswalk",
                    "population": None,
                    "building_population": 0.0,
                    "error": "No verified name/province match; Cadastre ID is not INE",
                }
            )
            continue
        try:
            buildings = gpd.read_file(path)
            result = allocate_population_to_buildings(
                buildings,
                metadata[0],
                metadata[1],
                metadata[2],
            )
        except Exception as error:
            totals["skipped_files"] += 1
            audit.append(
                {
                    "municipality_id": municipality_id,
                    "status": "error",
                    "population": metadata[2],
                    "building_population": 0.0,
                    "error": str(error),
                }
            )
            continue
        totals["valid_files"] += 1
        totals["buildings"] += len(result)
        estimated = float(result["estimated_population"].sum())
        audit.append(
            {
                "municipality_id": municipality_id,
                "status": "ok",
                "population": metadata[2],
                "building_population": estimated,
                "error": "",
            }
        )
        if result.empty:
            continue
        frame = pd.DataFrame(result.drop(columns="geometry"))
        connection.register("_building_population_chunk", frame)
        try:
            connection.execute(
                """
                INSERT INTO building_population
                    (building_id, municipality_id, x, y, estimated_population,
                     residential_use, building_source)
                SELECT building_id, municipality_id, x, y, estimated_population,
                       '1_residential', 'cadastre'
                FROM _building_population_chunk
                """
            )
        finally:
            connection.unregister("_building_population_chunk")
    if audit_path:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=audit[0].keys() if audit else [])
            if audit:
                writer.writeheader()
                writer.writerows(audit)
    return totals


def _name_key(value: str) -> str:
    """Normalize municipality names for cadastral-to-INE matching."""
    return name_key(value)


def _output_columns() -> list[str]:
    return [
        "building_id",
        "municipality_id",
        "municipality_name",
        "x",
        "y",
        "estimated_population",
        "geometry",
    ]


def main() -> None:
    """Prepare cadastral building population estimates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--footprints",
        type=Path,
        default=Path("data/raw/catastro_buildings/footprints"),
    )
    parser.add_argument(
        "--audit", type=Path, default=Path("reports/building_population_audit.csv")
    )
    args = parser.parse_args()
    with duckdb.connect(str(args.database)) as connection:
        totals = prepare_building_population(connection, args.footprints, args.audit)
    print(totals)


if __name__ == "__main__":
    main()
