"""Render a continuous nearest-hospital driving-time gradient."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import duckdb
import geopandas as gpd
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import shapely
from matplotlib.colors import Normalize
from pyproj import Transformer
from sklearn.neighbors import NearestNeighbors
from tqdm import tqdm

from desfibrilator.accessibility import _accepted_aeds
from desfibrilator.map import _add_ign_basemap


@dataclass(frozen=True)
class IsochroneStats:
    """Summary of the rendered travel-time surface."""

    minimum_minutes: float
    maximum_minutes: float
    mapped_aeds: int
    reachable_aeds: int


def render_isochrone(
    connection: duckdb.DuckDBPyConnection,
    output_path: Path,
    grid_size: int = 220,
    add_basemap: bool = True,
    boundary_path: Path = Path("data/interim/castilla_y_leon_boundary.gpkg"),
) -> IsochroneStats:
    """Render a nearest-emergency-hospital time surface over Castilla y León.

    The surface uses the nearest routed road-node value for each grid cell. No
    fixed upper color limit is applied: the color scale spans the valid values
    in the current run.
    """
    if grid_size < 20:
        raise ValueError("grid_size must be at least 20")
    nodes = connection.sql(
        """
        SELECT n.longitude, n.latitude, a.network_time_minutes
        FROM road_nodes AS n
        JOIN node_hospital_access AS a USING (node_id)
        WHERE a.access_status = 'reachable'
          AND a.network_time_minutes IS NOT NULL
        """
    ).df()
    if nodes.empty:
        raise ValueError("No reachable node access values; run accessibility first")

    values = nodes["network_time_minutes"].to_numpy(float)
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    color_maximum = maximum if maximum > minimum else minimum + 1.0
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    boundary = gpd.read_file(boundary_path).to_crs("EPSG:3857")
    if boundary.empty:
        raise ValueError(f"Regional boundary is empty: {boundary_path}")
    region_geometry = boundary.geometry.union_all()
    node_x, node_y = transformer.transform(
        nodes["longitude"].to_numpy(float), nodes["latitude"].to_numpy(float)
    )
    x_min, y_min, x_max, y_max = boundary.total_bounds
    x_values = np.linspace(x_min, x_max, grid_size)
    y_values = np.linspace(y_min, y_max, grid_size)
    grid_x, grid_y = np.meshgrid(x_values, y_values)
    valid = np.column_stack((node_x, node_y))
    nearest = NearestNeighbors(n_neighbors=1, algorithm="auto").fit(valid)
    grid_points = np.column_stack((grid_x.ravel(), grid_y.ravel()))
    indices = []
    batch_size = grid_size * 10
    for start in tqdm(
        range(0, len(grid_points), batch_size),
        desc="Rendering travel-time grid",
        unit="batch",
    ):
        _, batch_indices = nearest.kneighbors(grid_points[start : start + batch_size])
        indices.append(batch_indices[:, 0])
    grid_values = values[np.concatenate(indices)].reshape(grid_x.shape)
    inside_region = shapely.covers(
        region_geometry, shapely.points(grid_x.ravel(), grid_y.ravel())
    ).reshape(grid_x.shape)
    grid_values = np.ma.array(grid_values, mask=~inside_region)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(12, 10), dpi=180)
    axis.set_xlim(x_min, x_max)
    axis.set_ylim(y_min, y_max)
    if add_basemap:
        _add_ign_basemap(axis)
    mesh = axis.pcolormesh(
        grid_x,
        grid_y,
        grid_values,
        cmap="RdYlGn_r",
        norm=Normalize(vmin=minimum, vmax=color_maximum),
        shading="auto",
        alpha=0.66,
        zorder=1,
    )
    colorbar = figure.colorbar(mesh, ax=axis, shrink=0.75, pad=0.02)
    colorbar.set_label("Driving time to nearest emergency hospital (minutes)")

    hospitals = connection.sql(
        """
        SELECT name, longitude, latitude
        FROM hospitals
        WHERE emergency_capable = true
          AND longitude IS NOT NULL AND latitude IS NOT NULL
        ORDER BY hospital_id
        """
    ).df()
    if not hospitals.empty:
        hospital_x, hospital_y = transformer.transform(
            hospitals["longitude"].to_numpy(float),
            hospitals["latitude"].to_numpy(float),
        )
        axis.scatter(
            hospital_x,
            hospital_y,
            marker="*",
            s=70,
            c="white",
            edgecolors="#111827",
            linewidths=0.7,
            label="Emergency hospital",
            zorder=4,
        )

    aed_results = connection.sql(
        """
        SELECT aed_id, network_time_minutes
        FROM aed_hospital_access
        WHERE access_status = 'reachable'
        ORDER BY aed_id
        """
    ).df()
    aed_locations = {row["aed_id"]: row for row in _accepted_aeds(connection)}
    aed_results["longitude"] = aed_results["aed_id"].map(
        lambda value: aed_locations.get(value, {}).get("longitude")
    )
    aed_results["latitude"] = aed_results["aed_id"].map(
        lambda value: aed_locations.get(value, {}).get("latitude")
    )
    aed_results = aed_results.dropna(subset=["longitude", "latitude"])
    if not aed_results.empty:
        aed_x, aed_y = transformer.transform(
            aed_results["longitude"].to_numpy(float),
            aed_results["latitude"].to_numpy(float),
        )
        axis.scatter(
            aed_x,
            aed_y,
            c=aed_results["network_time_minutes"].to_numpy(float),
            cmap="RdYlGn_r",
            norm=Normalize(vmin=minimum, vmax=color_maximum),
            s=13,
            edgecolors="white",
            linewidths=0.25,
            label="AED",
            zorder=5,
        )
    axis.legend(loc="lower left", frameon=True, framealpha=0.9)
    axis.set_title(
        "Driving time from AED locations to emergency hospitals", fontsize=15
    )
    axis.set_axis_off()
    figure.text(
        0.01,
        0.01,
        "Road network: OpenStreetMap/Geofabrik; hospitals: configured source; "
        "basemap: IGN Mapa Base, CC BY 4.0",
        fontsize=7,
        color="#444444",
    )
    figure.tight_layout(pad=0.5)
    figure.savefig(output_path, format="png", bbox_inches="tight")
    plt.close(figure)

    mapped_aeds = connection.sql(
        "SELECT count(*) FROM aed_hospital_access WHERE access_status != 'unsnapped'"
    ).fetchone()[0]
    reachable_aeds = connection.sql(
        "SELECT count(*) FROM aed_hospital_access WHERE access_status = 'reachable'"
    ).fetchone()[0]
    return IsochroneStats(minimum, maximum, mapped_aeds, reachable_aeds)


def _region_extent(
    connection, transformer: Transformer
) -> tuple[float, float, float, float]:
    """Return a projected extent based on the municipality source points."""
    bounds = connection.sql(
        """
        SELECT min(longitude), min(latitude), max(longitude), max(latitude)
        FROM municipalities
        WHERE longitude IS NOT NULL AND latitude IS NOT NULL
        """
    ).fetchone()
    if bounds[0] is None:
        bounds = connection.sql(
            """
            SELECT min(longitude), min(latitude), max(longitude), max(latitude)
            FROM road_nodes
            """
        ).fetchone()
    west, south, east, north = bounds
    x_min, y_min = transformer.transform(west, south)
    x_max, y_max = transformer.transform(east, north)
    if x_min == x_max:
        x_min -= 1_000
        x_max += 1_000
    if y_min == y_max:
        y_min -= 1_000
        y_max += 1_000
    return x_min, y_min, x_max, y_max


def main() -> None:
    """Render the configured travel-time gradient."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/figures/aed_hospital_isochrone.png"),
    )
    parser.add_argument("--grid-size", type=int, default=220)
    parser.add_argument("--no-basemap", action="store_true")
    parser.add_argument(
        "--boundary",
        type=Path,
        default=Path("data/interim/castilla_y_leon_boundary.gpkg"),
    )
    args = parser.parse_args()
    with duckdb.connect(str(args.database), read_only=True) as connection:
        stats = render_isochrone(
            connection,
            args.output,
            args.grid_size,
            not args.no_basemap,
            args.boundary,
        )
    print(
        f"Wrote {args.output}: {stats.minimum_minutes:.1f}-{stats.maximum_minutes:.1f} "
        f"minutes; {stats.reachable_aeds}/{stats.mapped_aeds} AEDs reachable"
    )


if __name__ == "__main__":
    main()
