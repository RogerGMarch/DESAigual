"""Estimate population covered by AEDs on a walking network."""

import argparse
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from pyproj import Transformer
from tqdm import tqdm

from desfibrilator.accessibility import _accepted_aeds, _insert_frame
from desfibrilator.network import create_walking_snapper, load_pandana_walking_network
from desfibrilator.schema import create_schema

THRESHOLDS = (5.0, 10.0, 15.0)


def compute_population_access(
    connection: duckdb.DuckDBPyConnection,
    thresholds: tuple[float, ...] = THRESHOLDS,
    cell_size_m: float = 10_000.0,
    chunk_size: int = 100_000,
    search_minutes: float = 360.0,
) -> dict[str, int | float]:
    """Assign building population to nearest AED walking-time catchments."""
    if not thresholds or any(value <= 0 for value in thresholds):
        raise ValueError("thresholds must contain positive minutes")
    if search_minutes < max(thresholds):
        raise ValueError("search_minutes must include all reporting thresholds")
    create_schema(connection)
    buildings = connection.sql("SELECT count(*) FROM building_population").fetchone()[0]
    if not buildings:
        raise ValueError("building_population is empty; prepare buildings first")
    network = load_pandana_walking_network(connection)
    snapper = create_walking_snapper(connection, max_distance_m=500.0)
    to_wgs84 = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)
    aeds = pd.DataFrame(_accepted_aeds(connection))
    if aeds.empty:
        raise ValueError("No accepted AED coordinates are available")
    aeds = aeds.reset_index(drop=True)
    aeds["node_id"] = snapper(aeds["longitude"], aeds["latitude"])
    aeds = aeds.dropna(subset=["node_id"]).reset_index(drop=True)
    if aeds.empty:
        raise ValueError(
            "No accepted AEDs are within 500 metres of substantial walking nodes"
        )
    max_threshold = float(search_minutes)
    network.set_pois(
        category="aed",
        maxdist=max_threshold,
        maxitems=1,
        x_col=aeds["longitude"],
        y_col=aeds["latitude"],
    )
    nearest = network.nearest_pois(
        max_threshold,
        "aed",
        num_pois=1,
        max_distance=max_threshold,
        include_poi_ids=True,
    )
    node_times = pd.to_numeric(nearest[1], errors="coerce")
    node_pois = pd.to_numeric(nearest["poi1"], errors="coerce")
    node_access = pd.DataFrame(
        {
            "node_id": nearest.index.astype("int64"),
            "walk_time_minutes": node_times,
            "nearest_aed_id": node_pois.map(dict(enumerate(aeds["aed_id"].tolist()))),
        }
    ).reset_index(drop=True)
    unreachable_nodes = node_times.to_numpy() >= max_threshold
    node_access.loc[unreachable_nodes, "walk_time_minutes"] = np.nan
    node_access.loc[unreachable_nodes, "nearest_aed_id"] = None

    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute("DELETE FROM building_aed_access")
        connection.execute("DELETE FROM municipality_population_access")
        connection.execute("DELETE FROM population_access_grid")
        building_data = connection.sql(
            """
            SELECT building_id, municipality_id, x, y, estimated_population
            FROM building_population
            """
        ).df()
        grid_parts = []
        municipality_parts = []
        total_population = 0.0
        covered_population = {threshold: 0.0 for threshold in thresholds}
        for start in tqdm(
            range(0, len(building_data), chunk_size),
            total=(buildings + chunk_size - 1) // chunk_size,
            desc="Calculating building AED access",
            unit="chunk",
        ):
            buildings_frame = building_data.iloc[start : start + chunk_size].copy()
            longitudes, latitudes = to_wgs84.transform(
                buildings_frame["x"].to_numpy(float),
                buildings_frame["y"].to_numpy(float),
            )
            node_ids = snapper(longitudes, latitudes)
            buildings_frame["node_id"] = list(node_ids)
            result = buildings_frame.merge(node_access, on="node_id", how="left")
            for threshold in thresholds:
                result[f"access_{int(threshold)}_minutes"] = (
                    result["walk_time_minutes"] <= threshold
                )
            result = result.drop(columns=["x", "y", "node_id"])
            _insert_frame(
                connection,
                result,
                "building_aed_access",
                [
                    "building_id",
                    "municipality_id",
                    "estimated_population",
                    "walk_time_minutes",
                    "nearest_aed_id",
                    *[f"access_{int(t)}_minutes" for t in thresholds],
                ],
                "Writing building AED access",
                chunk_size=chunk_size,
            )
            total_population += float(result["estimated_population"].sum())
            for threshold in thresholds:
                covered_population[threshold] += float(
                    result.loc[
                        result[f"access_{int(threshold)}_minutes"],
                        "estimated_population",
                    ].sum()
                )
            result["cell_x"] = (
                np.floor(buildings_frame["x"] / cell_size_m) * cell_size_m
                + cell_size_m / 2
            ).to_numpy()
            result["cell_y"] = (
                np.floor(buildings_frame["y"] / cell_size_m) * cell_size_m
                + cell_size_m / 2
            ).to_numpy()
            grid_parts.append(_aggregate_grid(result, thresholds, cell_size_m))
            municipality_parts.append(_aggregate_municipality(result, thresholds))

        grid = (
            pd.concat(grid_parts, ignore_index=True)
            .groupby(["cell_id", "x", "y", "cell_size_m"], as_index=False)
            .sum()
        )
        municipality = (
            pd.concat(municipality_parts, ignore_index=True)
            .groupby(["municipality_id"], as_index=False)
            .sum()
        )
        _insert_frame(
            connection,
            grid,
            "population_access_grid",
            [
                "cell_id",
                "x",
                "y",
                "cell_size_m",
                "population_total",
                *[f"population_{int(t)}_minutes" for t in thresholds],
            ],
            "Writing population grid",
        )
        municipality_names = connection.sql(
            "SELECT cod_ine, municipio FROM municipalities"
        ).df()
        municipality = municipality.merge(
            municipality_names.rename(
                columns={"cod_ine": "municipality_id", "municipio": "municipality_name"}
            ),
            on="municipality_id",
            how="left",
        )
        municipality["buildings_total"] = municipality["buildings_total"].astype(
            "int64"
        )
        municipality["buildings_with_population"] = municipality[
            "buildings_with_population"
        ].astype("int64")
        _insert_frame(
            connection,
            municipality,
            "municipality_population_access",
            [
                "municipality_id",
                "municipality_name",
                "population_total",
                *[f"population_{int(t)}_minutes" for t in thresholds],
                "buildings_total",
                "buildings_with_population",
            ],
            "Writing municipality access",
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return {
        "buildings": int(buildings),
        "aed_count": len(aeds),
        "population": total_population,
        **{f"population_{int(t)}_minutes": covered_population[t] for t in thresholds},
    }


def render_population_access_map(
    connection: duckdb.DuckDBPyConnection,
    output_path: Path,
    thresholds: tuple[float, ...] = THRESHOLDS,
    add_basemap: bool = True,
) -> None:
    """Render percentage of estimated population covered at each threshold."""
    grid = connection.sql(
        """
        SELECT x, y, cell_size_m, population_total,
               population_5_minutes, population_10_minutes,
               population_15_minutes
        FROM population_access_grid
        """
    ).df()
    if grid.empty:
        raise ValueError("population_access_grid is empty; run population access first")
    grid["x"] = grid["x"].astype(float)
    grid["y"] = grid["y"].astype(float)
    x_values = np.sort(grid["x"].unique())
    y_values = np.sort(grid["y"].unique())
    transformer = Transformer.from_crs("EPSG:25830", "EPSG:3857", always_xy=True)
    x_min, y_min = transformer.transform(
        x_values.min() - grid.cell_size_m.iloc[0] / 2,
        y_values.min() - grid.cell_size_m.iloc[0] / 2,
    )
    x_max, y_max = transformer.transform(
        x_values.max() + grid.cell_size_m.iloc[0] / 2,
        y_values.max() + grid.cell_size_m.iloc[0] / 2,
    )
    figure, axes = plt.subplots(1, len(thresholds), figsize=(18, 8), squeeze=False)
    for axis, threshold in zip(axes[0], thresholds, strict=True):
        value = grid[f"population_{int(threshold)}_minutes"] / grid["population_total"]
        grid[f"coverage_{int(threshold)}"] = (value * 100).where(
            grid["population_total"] > 0
        )
        matrix = grid.pivot(index="y", columns="x", values=f"coverage_{int(threshold)}")
        matrix = matrix.reindex(index=y_values, columns=x_values)
        axis.set_xlim(x_min, x_max)
        axis.set_ylim(y_min, y_max)
        if add_basemap:
            from desfibrilator.map import _add_ign_basemap

            _add_ign_basemap(axis)
        image = axis.imshow(
            matrix.to_numpy(float),
            extent=(x_min, x_max, y_min, y_max),
            origin="lower",
            cmap="YlGn",
            norm=Normalize(vmin=0, vmax=100),
            alpha=0.75,
            interpolation="nearest",
            zorder=1,
        )
        axis.set_title(f"Population within {int(threshold)} minutes")
        axis.set_axis_off()
    figure.colorbar(
        image, ax=axes.ravel().tolist(), label="Estimated population covered (%)"
    )
    figure.suptitle("Population access to AEDs by walking time", fontsize=16)
    figure.text(
        0.01,
        0.01,
        "Population allocated to residential cadastral footprints with Tobler "
        "area interpolation; "
        "walking network: OpenStreetMap/Geofabrik",
        fontsize=7,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _aggregate_grid(
    frame: pd.DataFrame, thresholds, cell_size_m: float
) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "cell_id": frame["cell_x"].astype(int).astype(str)
            + ":"
            + frame["cell_y"].astype(int).astype(str),
            "x": frame["cell_x"],
            "y": frame["cell_y"],
            "cell_size_m": cell_size_m,
            "population_total": frame["estimated_population"],
        }
    )
    for threshold in thresholds:
        result[f"population_{int(threshold)}_minutes"] = frame.loc[
            frame[f"access_{int(threshold)}_minutes"], "estimated_population"
        ].reindex(frame.index, fill_value=0)
    return result.groupby(["cell_id", "x", "y", "cell_size_m"], as_index=False).sum()


def _aggregate_municipality(frame: pd.DataFrame, thresholds) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "municipality_id": frame["municipality_id"],
            "population_total": frame["estimated_population"],
            "buildings_total": 1,
            "buildings_with_population": (frame["estimated_population"] > 0).astype(
                int
            ),
        }
    )
    for threshold in thresholds:
        result[f"population_{int(threshold)}_minutes"] = frame.loc[
            frame[f"access_{int(threshold)}_minutes"], "estimated_population"
        ].reindex(frame.index, fill_value=0)
    return result.groupby("municipality_id", as_index=False).sum()


def main() -> None:
    """Compute building population access and render its coverage map."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("reports/figures/population_aed_access.png")
    )
    parser.add_argument("--skip-map", action="store_true")
    parser.add_argument("--search-minutes", type=float, default=360.0)
    args = parser.parse_args()
    with duckdb.connect(str(args.database)) as connection:
        stats = compute_population_access(
            connection, search_minutes=args.search_minutes
        )
        if not args.skip_map:
            render_population_access_map(connection, args.output)
    print(stats)


if __name__ == "__main__":
    main()
