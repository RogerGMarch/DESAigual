"""Calculate AED-to-emergency-hospital travel times with Pandana."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import duckdb
from tqdm import tqdm

from desfibrilator.network import load_pandana_network
from desfibrilator.normalize import address_key
from desfibrilator.schema import create_schema


@dataclass(frozen=True)
class AccessibilityStats:
    """Counts and coverage information for one accessibility run."""

    network_nodes: int
    emergency_hospitals: int
    reachable_nodes: int
    mapped_aeds: int
    reachable_aeds: int


def compute_accessibility(
    connection: duckdb.DuckDBPyConnection,
    max_search_minutes: float = 360.0,
) -> AccessibilityStats:
    """Calculate nearest emergency-hospital times for nodes and accepted AEDs.

    ``max_search_minutes`` limits the Pandana search to keep memory bounded. It
    is an algorithmic search limit, not a color-scale cap; reachable results
    below the limit retain their actual travel times.
    """
    if max_search_minutes <= 0:
        raise ValueError("max_search_minutes must be greater than zero")
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("Accessibility requires pandas and Pandana") from error
    create_schema(connection)
    node_count = connection.sql("SELECT count(*) FROM road_nodes").fetchone()[0]
    if not node_count:
        raise ValueError("road_nodes is empty; run the network extraction first")
    hospitals = connection.sql(
        """
        SELECT hospital_id, name, longitude, latitude
        FROM hospitals
        WHERE emergency_capable = true
          AND longitude IS NOT NULL
          AND latitude IS NOT NULL
        ORDER BY hospital_id
        """
    ).df()
    if hospitals.empty:
        raise ValueError(
            "No emergency-capable hospitals with coordinates are available; "
            "load the hospital source first"
        )

    network = load_pandana_network(connection)
    hospitals = hospitals.reset_index(drop=True)
    category = "emergency_hospital"
    network.set_pois(
        category=category,
        maxdist=max_search_minutes,
        maxitems=1,
        x_col=hospitals["longitude"],
        y_col=hospitals["latitude"],
    )
    nearest = network.nearest_pois(
        max_search_minutes,
        category,
        num_pois=1,
        max_distance=max_search_minutes,
        include_poi_ids=True,
    )
    time_column = _column(nearest, 1, "1")
    poi_column = _column(nearest, "poi1")
    max_distance = float(max_search_minutes)
    distances = pd.to_numeric(nearest[time_column], errors="coerce")
    poi_indices = pd.to_numeric(nearest[poi_column], errors="coerce")
    hospital_lookup = dict(enumerate(hospitals["hospital_id"].tolist()))
    reachable = distances.notna() & distances.lt(max_distance)
    reachable &= (
        poi_indices.notna() & poi_indices.ge(0) & poi_indices.lt(len(hospitals))
    )
    node_frame = pd.DataFrame(
        {
            "node_id": nearest.index.astype("int64"),
            "hospital_id": poi_indices.map(hospital_lookup),
            "network_time_minutes": distances,
            "access_status": reachable.map({True: "reachable", False: "unreachable"}),
        }
    )
    node_frame.loc[~reachable, "hospital_id"] = None
    node_frame.loc[~reachable, "network_time_minutes"] = None
    node_frame = node_frame.reset_index(drop=True)

    aeds = _accepted_aeds(connection)
    mapped_aeds = 0
    if aeds:
        locations = pd.DataFrame(aeds)
        node_ids = network.get_node_ids(locations["longitude"], locations["latitude"])
        locations["node_id"] = list(node_ids)
        aed_frame = locations.merge(
            node_frame[
                [
                    "node_id",
                    "hospital_id",
                    "network_time_minutes",
                    "access_status",
                ]
            ],
            on="node_id",
            how="left",
        )
        aed_frame["access_status"] = aed_frame["access_status"].fillna(
            aed_frame["node_id"].notna().map({True: "unreachable", False: "unsnapped"})
        )
        aed_frame = aed_frame[
            [
                "aed_id",
                "node_id",
                "hospital_id",
                "network_time_minutes",
                "access_status",
            ]
        ]
        mapped_aeds = int(aed_frame["node_id"].notna().sum())
    else:
        aed_frame = pd.DataFrame(
            columns=[
                "aed_id",
                "node_id",
                "hospital_id",
                "network_time_minutes",
                "access_status",
            ]
        )

    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute("DELETE FROM node_hospital_access")
        _insert_frame(
            connection,
            node_frame,
            "node_hospital_access",
            ["node_id", "hospital_id", "network_time_minutes", "access_status"],
            "Writing node access",
        )
        connection.execute("DELETE FROM aed_hospital_access")
        _insert_frame(
            connection,
            aed_frame,
            "aed_hospital_access",
            [
                "aed_id",
                "node_id",
                "hospital_id",
                "network_time_minutes",
                "access_status",
            ],
            "Writing AED access",
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    reachable_aeds = int((aed_frame["access_status"] == "reachable").sum())
    return AccessibilityStats(
        network_nodes=len(node_frame),
        emergency_hospitals=len(hospitals),
        reachable_nodes=int((node_frame["access_status"] == "reachable").sum()),
        mapped_aeds=mapped_aeds,
        reachable_aeds=reachable_aeds,
    )


def _accepted_aeds(connection: duckdb.DuckDBPyConnection) -> list[dict]:
    """Read current accepted geocodes without changing the geocoding cache."""
    geocodes = {
        row[0]: row[1:]
        for row in connection.sql(
            """
            SELECT address_key, latitude, longitude, match_status
            FROM aed_geocodes
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """
        ).fetchall()
    }
    source_rows = connection.sql(
        "SELECT aed_id, address, municipality, province FROM aed_locations"
    ).fetchall()
    rows = []
    for aed_id, address, municipality, province in tqdm(
        source_rows, desc="Matching accepted AEDs", unit="AED"
    ):
        if not address:
            continue
        geocode = geocodes.get(address_key(address, municipality, province))
        if geocode is None or (
            geocode[2] is not None and not geocode[2].startswith("accepted")
        ):
            continue
        rows.append(
            {
                "aed_id": aed_id,
                "longitude": float(geocode[1]),
                "latitude": float(geocode[0]),
            }
        )
    return rows


def _insert_frame(
    connection: duckdb.DuckDBPyConnection,
    frame,
    table: str,
    columns: list[str],
    description: str,
    chunk_size: int = 100_000,
) -> None:
    """Insert a DataFrame in bounded chunks while reporting progress."""
    if frame.empty:
        return
    column_sql = ", ".join(columns)
    for start in tqdm(
        range(0, len(frame), chunk_size),
        desc=description,
        unit="rows",
        total=(len(frame) + chunk_size - 1) // chunk_size,
    ):
        chunk = frame.iloc[start : start + chunk_size][columns]
        connection.register("_access_chunk", chunk)
        try:
            connection.execute(
                f"INSERT INTO {table} ({column_sql}) "
                f"SELECT {column_sql} FROM _access_chunk"
            )
        finally:
            connection.unregister("_access_chunk")


def _column(frame, *names):
    for name in names:
        if name in frame.columns:
            return name
    raise ValueError(f"Pandana result is missing one of columns {names!r}")


def main() -> None:
    """Calculate accessibility using the current accepted AED geocodes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument("--search-minutes", type=float, default=360.0)
    args = parser.parse_args()
    with duckdb.connect(str(args.database)) as connection:
        stats = compute_accessibility(connection, args.search_minutes)
    print(
        f"Accessibility: {stats.reachable_aeds}/{stats.mapped_aeds} AEDs and "
        f"{stats.reachable_nodes}/{stats.network_nodes} nodes reachable from "
        f"{stats.emergency_hospitals} hospitals"
    )


if __name__ == "__main__":
    main()
