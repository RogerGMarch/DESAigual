"""Fill missing municipality building populations from OpenStreetMap."""

import argparse
import csv
import time
from pathlib import Path

import duckdb
import geopandas as gpd
import httpx
import pandas as pd
from pyproj import Transformer
from pyrosm import OSM
from tqdm import tqdm

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
NON_RESIDENTIAL_BUILDING_TYPES = {
    "barn",
    "bridge",
    "carport",
    "church",
    "commercial",
    "garage",
    "garages",
    "greenhouse",
    "industrial",
    "office",
    "roof",
    "school",
    "service",
    "shed",
    "stable",
    "storage_tank",
    "warehouse",
}
LOCAL_NOMINATIM_ENDPOINT = "https://osm.vcity.tech/nominatim/search.php"


def fill_missing_municipalities(
    connection: duckdb.DuckDBPyConnection,
    pbf_path: Path,
    audit_path: Path | None = None,
) -> dict[str, int | float]:
    """Allocate official population to OSM buildings for missing municipalities."""
    if not pbf_path.exists():
        raise FileNotFoundError(pbf_path)
    create_schema(connection)
    official = {
        str(row[2]): (row[0], float(row[3] or 0), str(row[1]).zfill(2))
        for row in connection.sql(
            "SELECT municipio, cod_provincia, cod_ine, poblacion FROM municipalities"
        ).fetchall()
    }
    missing = {
        str(row[0])
        for row in connection.sql(
            """
            SELECT m.cod_ine
            FROM municipalities AS m
            LEFT JOIN (
                SELECT DISTINCT municipality_id
                FROM building_population
            ) AS b ON b.municipality_id = m.cod_ine
            WHERE b.municipality_id IS NULL
            """
        ).fetchall()
    }
    if not missing:
        return {"municipalities": 0, "buildings": 0, "population": 0.0}

    boundaries = OSM(str(pbf_path), engine="in_memory", workers=1).get_boundaries(
        extra_attributes=["ine:municipio"]
    )
    boundaries = boundaries[boundaries["admin_level"].astype(str) == "8"].copy()
    boundaries["municipality_id"] = (
        boundaries["ine:municipio"].fillna("").astype(str).str[:5]
    )
    targets = boundaries[boundaries["municipality_id"].isin(missing)].copy()
    if set(targets["municipality_id"]) != missing:
        unresolved = sorted(missing - set(targets["municipality_id"]))
        raise ValueError(f"OSM has no municipality boundaries for {unresolved}")
    targets["province_code"] = targets["municipality_id"].map(
        lambda value: official[value][2]
    )

    audit = []
    total_buildings = 0
    total_population = 0.0
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            "DELETE FROM building_population WHERE municipality_id IN "
            "(SELECT unnest(?))",
            [list(missing)],
        )
        for province, province_targets in tqdm(
            targets.groupby("province_code"),
            desc="OSM fallback provinces",
            unit="province-group",
        ):
            del province
            region = province_targets.geometry.union_all()
            buildings = OSM(
                str(pbf_path), engine="in_memory", workers=1, bounding_box=region
            ).get_buildings()
            buildings = buildings[
                buildings.geometry.notna() & ~buildings.geometry.is_empty
            ].copy()
            buildings["_row_id"] = range(len(buildings))
            points = gpd.GeoDataFrame(
                buildings["_row_id"].to_frame(),
                geometry=buildings.geometry.representative_point(),
                crs=buildings.crs,
            )
            assignment = gpd.sjoin(
                points,
                province_targets[["municipality_id", "geometry"]],
                how="inner",
                predicate="within",
            )
            assignment = assignment.drop_duplicates("_row_id")
            assigned = dict(
                zip(
                    assignment["_row_id"].astype(int),
                    assignment["municipality_id"].astype(str),
                    strict=True,
                )
            )
            buildings["municipality_id"] = buildings["_row_id"].map(assigned)
            buildings = buildings.dropna(subset=["municipality_id"])
            for municipality_id, municipality_buildings in tqdm(
                buildings.groupby("municipality_id"),
                desc="Allocating OSM municipalities",
                unit="municipality",
                leave=False,
            ):
                metadata = official[municipality_id]
                candidates = _residential_candidates(municipality_buildings)
                if candidates.empty:
                    audit.append(_audit_row(municipality_id, metadata, "empty", 0, 0))
                    continue
                candidates["localId"] = [
                    f"OSM-{value}" for value in candidates["id"].astype(str)
                ]
                result = allocate_population_to_buildings(
                    candidates,
                    municipality_id,
                    metadata[0],
                    metadata[1],
                )
                frame = pd.DataFrame(result.drop(columns="geometry"))
                frame["residential_use"] = "osm_residential"
                frame["building_source"] = "osm_fallback"
                connection.register("_osm_population_chunk", frame)
                try:
                    connection.execute(
                        """
                        INSERT INTO building_population
                            (building_id, municipality_id, x, y,
                             estimated_population, residential_use, building_source)
                        SELECT building_id, municipality_id, x, y,
                               estimated_population, residential_use, building_source
                        FROM _osm_population_chunk
                        """
                    )
                finally:
                    connection.unregister("_osm_population_chunk")
                estimate = float(result["estimated_population"].sum())
                total_buildings += len(result)
                total_population += estimate
                audit.append(
                    _audit_row(
                        municipality_id,
                        metadata,
                        "osm_fallback",
                        len(result),
                        estimate,
                    )
                )
        unresolved = missing - {
            row["municipality_id"] for row in audit if row["status"] == "osm_fallback"
        }
        for row in tqdm(
            _nominatim_population_points(unresolved, official),
            total=len(unresolved),
            desc="Locating point-only municipalities",
            unit="municipality",
        ):
            frame = pd.DataFrame([row])
            connection.register("_nominatim_population", frame)
            try:
                connection.execute(
                    """
                    INSERT INTO building_population
                        (building_id, municipality_id, x, y,
                         estimated_population, residential_use, building_source)
                    SELECT building_id, municipality_id, x, y,
                           estimated_population, residential_use, building_source
                    FROM _nominatim_population
                    """
                )
            finally:
                connection.unregister("_nominatim_population")
            metadata = official[row["municipality_id"]]
            audit.append(
                _audit_row(
                    row["municipality_id"],
                    metadata,
                    "nominatim_point",
                    0,
                    row["estimated_population"],
                )
            )
            total_population += row["estimated_population"]
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

    if audit_path:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=audit[0].keys())
            writer.writeheader()
            writer.writerows(audit)
    return {
        "municipalities": len(audit),
        "buildings": total_buildings,
        "population": total_population,
    }


def _residential_candidates(buildings: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Select residential OSM types, with a conservative fallback."""
    if "building" not in buildings.columns:
        return buildings.copy()
    types = buildings["building"].fillna("").astype(str)
    residential = buildings[types.isin(RESIDENTIAL_BUILDING_TYPES | {"yes"})].copy()
    if not residential.empty:
        return residential
    return buildings[~types.isin(NON_RESIDENTIAL_BUILDING_TYPES)].copy()


def _audit_row(municipality_id, metadata, status, buildings, estimate):
    return {
        "municipality_id": municipality_id,
        "municipality_name": metadata[0],
        "province_code": metadata[2],
        "official_population": metadata[1],
        "estimated_population": estimate,
        "buildings": buildings,
        "status": status,
    }


def _nominatim_population_points(municipality_ids, official):
    """Locate municipalities with no OSM buildings as population points."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:25830", always_xy=True)
    with httpx.Client(
        timeout=30,
        headers={"User-Agent": "desfibrilator-population-access/0.1"},
    ) as client:
        for municipality_id in sorted(municipality_ids):
            municipality, _, _ = official[municipality_id]
            results = _request_nominatim(client, municipality)
            if not results:
                continue
            longitude = float(results[0]["lon"])
            latitude = float(results[0]["lat"])
            x, y = transformer.transform(longitude, latitude)
            yield {
                "building_id": f"NOMINATIM:{municipality_id}",
                "municipality_id": municipality_id,
                "x": x,
                "y": y,
                "estimated_population": official[municipality_id][1],
                "residential_use": "nominatim_point",
                "building_source": "nominatim_point",
            }


def _request_nominatim(client: httpx.Client, municipality: str) -> list[dict]:
    """Request one local Nominatim result with bounded retries."""
    params = {
        "q": f"{municipality}, Castilla y Leon, Spain",
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "es",
    }
    for attempt in range(3):
        try:
            response = client.get(LOCAL_NOMINATIM_ENDPOINT, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            if attempt == 2:
                print(f"Nominatim unresolved {municipality}: {error}")
            else:
                time.sleep(2**attempt)
    return []


def main() -> None:
    """Fill missing municipality building populations from OSM."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--pbf", type=Path, default=Path("data/raw/castilla-y-leon-latest.osm.pbf")
    )
    parser.add_argument(
        "--audit", type=Path, default=Path("reports/osm_fallback_audit.csv")
    )
    args = parser.parse_args()
    with duckdb.connect(str(args.database)) as connection:
        stats = fill_missing_municipalities(connection, args.pbf, args.audit)
    print(stats)


if __name__ == "__main__":
    main()
