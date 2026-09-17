"""Build and persist a directed driving network from an OSM PBF."""

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
from tqdm import tqdm

from desfibrilator.schema import create_schema

DEFAULT_SPEEDS_KMH = {
    "motorway": 120.0,
    "motorway_link": 80.0,
    "trunk": 90.0,
    "trunk_link": 70.0,
    "primary": 70.0,
    "primary_link": 50.0,
    "secondary": 60.0,
    "secondary_link": 40.0,
    "tertiary": 50.0,
    "tertiary_link": 35.0,
    "unclassified": 40.0,
    "residential": 30.0,
    "living_street": 20.0,
    "service": 15.0,
}
WALKING_SPEED_KMH = 4.8


@dataclass(frozen=True)
class NetworkStats:
    """Counts describing a persisted driving network."""

    nodes: int
    raw_edges: int
    directed_edges: int


def parse_speed_kmh(
    value: Any,
    highway: str | None = None,
    defaults: dict[str, float] | None = None,
) -> float:
    """Return a speed in km/h from common OSM ``maxspeed`` values.

    Values without a unit are interpreted as km/h. For missing or unusable
    values, the configured highway-class default is used.
    """
    defaults = defaults or DEFAULT_SPEEDS_KMH
    text = "" if value is None else str(value).strip().lower()
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(mph|km/?h|kph)?", text)
    if match:
        speed = float(match.group(1).replace(",", "."))
        if match.group(2) == "mph":
            speed *= 1.609344
        if speed > 0:
            return speed
    return defaults.get(str(highway), 30.0)


def travel_time_minutes(
    length_m: float,
    maxspeed: Any,
    highway: str | None = None,
    defaults: dict[str, float] | None = None,
) -> float:
    """Calculate free-flow travel time for one road segment."""
    if length_m < 0 or not math.isfinite(length_m):
        raise ValueError(f"Road length must be finite and non-negative: {length_m}")
    speed = parse_speed_kmh(maxspeed, highway, defaults)
    return length_m / (speed * 1000.0 / 60.0)


def is_oneway(value: Any, junction: Any = None) -> str:
    """Normalize an OSM direction tag to ``forward``, ``reverse`` or ``both``."""
    text = "" if value is None else str(value).strip().lower()
    if text in {"-1", "reverse"}:
        return "reverse"
    if text in {"yes", "true", "1", "forward"}:
        return "forward"
    if str(junction).strip().lower() == "roundabout":
        return "forward"
    return "both"


def prepare_directed_edges(edges, source_updated_at: str | None = None) -> list[tuple]:
    """Expand OSM road segments into explicit directed edge rows."""
    prepared = []
    for index, row in enumerate(
        tqdm(
            edges.itertuples(index=False),
            total=len(edges),
            desc="Preparing directed roads",
            unit="segment",
        )
    ):
        values = row._asdict()
        source = _required_int(values.get("u"), "u")
        target = _required_int(values.get("v"), "v")
        highway = _text(values.get("highway"))
        name = _text(values.get("name"))
        length = float(values.get("length", 0.0))
        speed = parse_speed_kmh(values.get("maxspeed"), highway)
        minutes = travel_time_minutes(length, speed, highway)
        direction = is_oneway(values.get("oneway"), values.get("junction"))
        geometry = values.get("geometry")
        geometry_wkt = geometry.wkt if geometry is not None else None
        base_id = str(values.get("id", index))
        directions = (
            ((source, target, "forward"),)
            if direction == "forward"
            else (
                ((target, source, "reverse"),)
                if direction == "reverse"
                else ((source, target, "forward"), (target, source, "reverse"))
            )
        )
        for suffix, (edge_source, edge_target, _) in enumerate(directions):
            prepared.append(
                (
                    f"{base_id}:{suffix}",
                    edge_source,
                    edge_target,
                    highway,
                    name,
                    length,
                    speed,
                    minutes,
                    geometry_wkt,
                    source_updated_at,
                )
            )
    return prepared


def prepare_walking_edges(edges, source_updated_at: str | None = None) -> list[tuple]:
    """Expand walkable OSM segments in both directions at walking speed."""
    prepared = []
    for index, row in enumerate(
        tqdm(
            edges.itertuples(index=False),
            total=len(edges),
            desc="Preparing walking roads",
            unit="segment",
        )
    ):
        values = row._asdict()
        source = _required_int(values.get("u"), "u")
        target = _required_int(values.get("v"), "v")
        length = float(values.get("length", 0.0))
        minutes = length / (WALKING_SPEED_KMH * 1000.0 / 60.0)
        geometry = values.get("geometry")
        geometry_wkt = geometry.wkt if geometry is not None else None
        base_id = str(values.get("id", index))
        for suffix, edge_source, edge_target in (
            (0, source, target),
            (1, target, source),
        ):
            prepared.append(
                (
                    f"{base_id}:{suffix}",
                    edge_source,
                    edge_target,
                    length,
                    minutes,
                    geometry_wkt,
                    source_updated_at,
                )
            )
    return prepared


def extract_driving_network(
    connection: duckdb.DuckDBPyConnection,
    pbf_path: Path,
    source_updated_at: str | None = None,
) -> NetworkStats:
    """Parse a PBF with Pyrosm and replace the persisted driving network."""
    try:
        import pandas as pd
        from pyrosm import OSM
    except ImportError as error:
        raise RuntimeError(
            "Network extraction requires the optional geospatial dependencies. "
            "Run `uv sync --all-extras`."
        ) from error

    if not pbf_path.exists():
        raise FileNotFoundError(pbf_path)
    osm = OSM(str(pbf_path), engine="out_of_core", workers="auto")
    nodes, edges = osm.get_network(
        "driving",
        extra_attributes=["maxspeed", "oneway", "junction"],
        nodes=True,
    )
    edge_rows = prepare_directed_edges(edges, source_updated_at)
    node_rows = []
    for row in tqdm(
        nodes.itertuples(index=False),
        total=len(nodes),
        desc="Preparing nodes",
        unit="node",
    ):
        if row.lon is not None and row.lat is not None:
            node_rows.append((int(row.id), float(row.lon), float(row.lat)))
    node_ids = {row[0] for row in node_rows}
    edge_rows = [row for row in edge_rows if row[1] in node_ids and row[2] in node_ids]

    create_schema(connection)
    connection.execute("DELETE FROM road_edges")
    connection.execute("DELETE FROM road_nodes")
    node_frame = pd.DataFrame(node_rows, columns=("node_id", "longitude", "latitude"))
    edge_frame = pd.DataFrame(
        edge_rows,
        columns=(
            "edge_id",
            "source_id",
            "target_id",
            "highway",
            "name",
            "length_m",
            "maxspeed_kmh",
            "travel_time_minutes",
            "geometry_wkt",
            "source_updated_at",
        ),
    )
    connection.register("_network_nodes", node_frame)
    connection.register("_network_edges", edge_frame)
    try:
        connection.execute(
            """
            INSERT INTO road_nodes (node_id, longitude, latitude)
            SELECT node_id, longitude, latitude FROM _network_nodes
            """
        )
        connection.execute(
            """
            INSERT INTO road_edges
                (edge_id, source_id, target_id, highway, name, length_m,
                 maxspeed_kmh, travel_time_minutes, geometry_wkt, source_updated_at)
            SELECT edge_id, source_id, target_id, highway, name, length_m,
                   maxspeed_kmh, travel_time_minutes, geometry_wkt,
                   source_updated_at
            FROM _network_edges
            """
        )
    finally:
        connection.unregister("_network_nodes")
        connection.unregister("_network_edges")
    return NetworkStats(len(node_rows), len(edges), len(edge_rows))


def extract_walking_network(
    connection: duckdb.DuckDBPyConnection,
    pbf_path: Path,
    source_updated_at: str | None = None,
) -> NetworkStats:
    """Parse a PBF and persist a bidirectional walking network."""
    try:
        import pandas as pd
        from pyrosm import OSM
    except ImportError as error:
        raise RuntimeError(
            "Walking extraction requires the optional geospatial dependencies."
        ) from error
    if not pbf_path.exists():
        raise FileNotFoundError(pbf_path)
    osm = OSM(str(pbf_path), engine="out_of_core", workers="auto")
    nodes, edges = osm.get_network("walking", nodes=True)
    edge_rows = prepare_walking_edges(edges, source_updated_at)
    node_rows = []
    for row in tqdm(
        nodes.itertuples(index=False),
        total=len(nodes),
        desc="Preparing walking nodes",
        unit="node",
    ):
        if row.lon is not None and row.lat is not None:
            node_rows.append((int(row.id), float(row.lon), float(row.lat)))
    node_ids = {row[0] for row in node_rows}
    edge_rows = [row for row in edge_rows if row[1] in node_ids and row[2] in node_ids]
    create_schema(connection)
    connection.execute("DELETE FROM walk_edges")
    connection.execute("DELETE FROM walk_nodes")
    node_frame = pd.DataFrame(node_rows, columns=("node_id", "longitude", "latitude"))
    edge_frame = pd.DataFrame(
        edge_rows,
        columns=(
            "edge_id",
            "source_id",
            "target_id",
            "length_m",
            "travel_time_minutes",
            "geometry_wkt",
            "source_updated_at",
        ),
    )
    connection.register("_walk_nodes", node_frame)
    connection.register("_walk_edges", edge_frame)
    try:
        connection.execute(
            "INSERT INTO walk_nodes (node_id, longitude, latitude) "
            "SELECT node_id, longitude, latitude FROM _walk_nodes"
        )
        connection.execute(
            """
            INSERT INTO walk_edges
                (edge_id, source_id, target_id, length_m, travel_time_minutes,
                 geometry_wkt, source_updated_at)
            SELECT edge_id, source_id, target_id, length_m, travel_time_minutes,
                   geometry_wkt, source_updated_at
            FROM _walk_edges
            """
        )
    finally:
        connection.unregister("_walk_nodes")
        connection.unregister("_walk_edges")
    return NetworkStats(len(node_rows), len(edges), len(edge_rows))


def compute_walking_components(
    connection: duckdb.DuckDBPyConnection,
    chunk_size: int = 500_000,
) -> dict[str, int]:
    """Label weakly connected walking-network components and their sizes."""
    import numpy as np
    import pandas as pd
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    create_schema(connection)
    node_ids = connection.sql(
        "SELECT node_id FROM walk_nodes ORDER BY node_id"
    ).df()["node_id"].to_numpy(dtype="int64")
    if not len(node_ids):
        raise ValueError("walk_nodes is empty; extract the walking network first")
    source_chunks = []
    target_chunks = []
    cursor = connection.execute("SELECT source_id, target_id FROM walk_edges")
    for frame in tqdm(
        _fetch_df_chunks(cursor, chunk_size),
        desc="Reading walking edges",
        unit="chunk",
    ):
        source_values = frame["source_id"].to_numpy("int64")
        target_values = frame["target_id"].to_numpy("int64")
        source_positions = np.searchsorted(node_ids, source_values)
        target_positions = np.searchsorted(node_ids, target_values)
        source_chunks.append(source_positions)
        target_chunks.append(target_positions)
    sources = np.concatenate(source_chunks)
    targets = np.concatenate(target_chunks)
    graph = coo_matrix(
        (np.ones(len(sources), dtype="uint8"), (sources, targets)),
        shape=(len(node_ids), len(node_ids)),
    )
    count, labels = connected_components(graph, directed=False, return_labels=True)
    sizes = np.bincount(labels, minlength=count)
    result = pd.DataFrame(
        {
            "node_id": node_ids,
            "component_id": labels.astype("int64"),
            "component_size": sizes[labels].astype("int64"),
        }
    )
    connection.execute("BEGIN TRANSACTION")
    try:
        for start in tqdm(
            range(0, len(result), chunk_size),
            desc="Writing walking components",
            unit="chunk",
        ):
            chunk = result.iloc[start : start + chunk_size]
            connection.register("_walk_components", chunk)
            try:
                connection.execute(
                    """
                    UPDATE walk_nodes AS nodes
                    SET component_id = components.component_id,
                        component_size = components.component_size
                    FROM _walk_components AS components
                    WHERE nodes.node_id = components.node_id
                    """
                )
            finally:
                connection.unregister("_walk_components")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return {
        "nodes": len(node_ids),
        "edges": len(sources),
        "components": int(count),
        "micro_component_nodes": int((sizes[labels] < 10).sum()),
    }


def snap_walking_points(
    connection: duckdb.DuckDBPyConnection,
    longitudes,
    latitudes,
    max_distance_m: float = 500.0,
):
    """Snap WGS84 points to substantial walking nodes within a metre limit."""
    snapper = create_walking_snapper(connection, max_distance_m)
    return snapper(longitudes, latitudes)


def create_walking_snapper(connection, max_distance_m: float = 500.0):
    """Create a reusable projected nearest-node snapper for the walking graph."""
    import numpy as np
    import pandas as pd
    from pyproj import Transformer
    from sklearn.neighbors import NearestNeighbors

    nodes = connection.sql(
        """
        SELECT node_id, longitude, latitude
        FROM walk_nodes
        WHERE component_size >= 10
        ORDER BY node_id
        """
    ).df()
    if nodes.empty:
        raise ValueError(
            "Walking components are not labeled or contain no substantial nodes"
        )
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:25830", always_xy=True)
    node_x, node_y = transformer.transform(
        nodes["longitude"].to_numpy(float), nodes["latitude"].to_numpy(float)
    )
    nearest = NearestNeighbors(n_neighbors=1).fit(np.column_stack((node_x, node_y)))

    def snap(longitudes, latitudes):
        point_x, point_y = transformer.transform(
            np.asarray(longitudes, dtype=float), np.asarray(latitudes, dtype=float)
        )
        distances, indices = nearest.kneighbors(
            np.column_stack((point_x, point_y))
        )
        result = pd.Series(
            nodes.iloc[indices[:, 0]]["node_id"].to_numpy(), dtype="Int64"
        )
        result[distances[:, 0] > max_distance_m] = pd.NA
        return result

    return snap


def load_pandana_network(connection: duckdb.DuckDBPyConnection):
    """Build a Pandana network from the persisted node and edge tables."""
    try:
        import pandana
        import pandas as pd
    except ImportError as error:
        raise RuntimeError(
            "Accessibility requires pandas and Pandana. Run `uv sync --all-extras`."
        ) from error

    nodes = connection.sql(
        "SELECT node_id, longitude, latitude FROM road_nodes ORDER BY node_id"
    ).df()
    edges = connection.sql(
        """
        SELECT source_id, target_id, travel_time_minutes
        FROM road_edges
        WHERE travel_time_minutes IS NOT NULL
        """
    ).df()
    if nodes.empty or edges.empty:
        raise ValueError("The persisted road network has no usable nodes or edges")
    node_ids = nodes["node_id"].astype("int64")
    return pandana.Network(
        nodes["longitude"].astype(float).set_axis(node_ids),
        nodes["latitude"].astype(float).set_axis(node_ids),
        edges["source_id"].astype("int64"),
        edges["target_id"].astype("int64"),
        pd.DataFrame(
            {"network_time_minutes": edges["travel_time_minutes"].astype(float)}
        ),
        twoway=False,
    )


def load_pandana_walking_network(connection: duckdb.DuckDBPyConnection):
    """Build a Pandana network from the persisted walking tables."""
    try:
        import pandana
        import pandas as pd
    except ImportError as error:
        raise RuntimeError("Walking accessibility requires Pandana") from error
    nodes = connection.sql(
        """
        SELECT node_id, longitude, latitude
        FROM walk_nodes
        WHERE component_size >= 10
        ORDER BY node_id
        """
    ).df()
    edges = connection.sql(
        """
        SELECT source_id, target_id, travel_time_minutes
        FROM walk_edges
        WHERE source_id IN (
            SELECT node_id FROM walk_nodes WHERE component_size >= 10
        )
          AND target_id IN (
            SELECT node_id FROM walk_nodes WHERE component_size >= 10
        )
        """
    ).df()
    if nodes.empty or edges.empty:
        raise ValueError("The persisted walking network is empty")
    node_ids = nodes["node_id"].astype("int64")
    return pandana.Network(
        nodes["longitude"].astype(float).set_axis(node_ids),
        nodes["latitude"].astype(float).set_axis(node_ids),
        edges["source_id"].astype("int64"),
        edges["target_id"].astype("int64"),
        pd.DataFrame(
            {"walking_time_minutes": edges["travel_time_minutes"].astype(float)}
        ),
        twoway=False,
    )


def _fetch_df_chunks(cursor, chunk_size: int):
    """Yield bounded DataFrame chunks from a DuckDB cursor."""
    while True:
        frame = cursor.fetch_df_chunk(chunk_size)
        if frame is None or frame.empty:
            return
        yield frame


def _required_int(value: Any, name: str) -> int:
    if value is None:
        raise ValueError(f"OSM edge is missing {name!r}")
    return int(value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def main() -> None:
    """Extract the configured OSM driving network."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pbf",
        type=Path,
        default=Path("data/raw/castilla-y-leon-latest.osm.pbf"),
    )
    parser.add_argument("--mode", choices=("driving", "walking"), default="driving")
    parser.add_argument(
        "--components", action="store_true", help="label walking graph components"
    )
    parser.add_argument(
        "--components-only",
        action="store_true",
        help="label an existing walking graph without extracting it",
    )
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument("--source-updated-at", default=None)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(args.database)) as connection:
        if args.components_only:
            if args.mode != "walking":
                raise ValueError("--components-only requires --mode walking")
            stats = None
        elif args.mode == "walking":
            stats = extract_walking_network(
                connection, args.pbf, args.source_updated_at
            )
        else:
            stats = extract_driving_network(
                connection, args.pbf, args.source_updated_at
            )
        if args.components:
            print(compute_walking_components(connection))
    if stats is not None:
        print(
            f"Wrote {args.mode} network: {stats.nodes} nodes, "
            f"{stats.directed_edges} directed edges ({stats.raw_edges} OSM segments)"
        )


if __name__ == "__main__":
    main()
