"""Render building-footprint AED access for León city."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import duckdb
import geopandas as gpd
import httpx
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D

from desfibrilator.accessibility import _accepted_aeds
from desfibrilator.map import _add_ign_basemap


@dataclass(frozen=True)
class LeonMapStats:
    """Counts and population totals represented in the León map."""

    buildings: int
    residential_buildings: int
    estimated_population: float
    population_5_minutes: float
    population_10_minutes: float
    population_15_minutes: float
    mapped_aeds: int


def create_leon_building_map(
    connection: duckdb.DuckDBPyConnection,
    building_path: Path,
    output_path: Path,
    export_path: Path | None = None,
    add_basemap: bool = True,
    municipality_id: str = "24089",
    city_name: str = "León",
    building_source: str = "Spanish Cadastre INSPIRE BU",
) -> LeonMapStats:
    """Render and optionally export cadastral buildings with AED access."""
    buildings = gpd.read_file(building_path)
    if buildings.crs is None:
        raise ValueError(f"Cadastral layer has no CRS: {building_path}")
    buildings = buildings.to_crs("EPSG:25830")
    buildings["building_id"] = [
        f"{municipality_id}:{value}"
        for value in buildings.get("localId", buildings.index).astype(str)
    ]
    access = connection.sql(
        """
        SELECT building_id, estimated_population, walk_time_minutes,
               nearest_aed_id, access_5_minutes, access_10_minutes,
               access_15_minutes
        FROM building_aed_access
        WHERE municipality_id = ?
        """,
        params=[municipality_id],
    ).df()
    joined = buildings.merge(access, on="building_id", how="left")
    residential = joined["estimated_population"].notna()
    joined["mapped_access"] = joined["walk_time_minutes"].notna()
    joined["within_15"] = joined["walk_time_minutes"].le(15)
    joined_3857 = joined.to_crs("EPSG:3857")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(12, 12), dpi=220)
    mapped_envelope = joined_3857[residential]
    x_min, y_min, x_max, y_max = mapped_envelope.total_bounds
    margin_x = (x_max - x_min) * 0.04
    margin_y = (y_max - y_min) * 0.04
    axis.set_xlim(x_min - margin_x, x_max + margin_x)
    axis.set_ylim(y_min - margin_y, y_max + margin_y)
    if add_basemap:
        try:
            _add_ign_basemap(axis)
        except httpx.HTTPError as error:
            print(f"Basemap unavailable for {city_name}: {error}")

    joined_3857.plot(
        ax=axis,
        facecolor="none",
        edgecolor="#9ca3af",
        linewidth=0.12,
        zorder=2,
    )
    colored = joined_3857[joined_3857["within_15"]].copy()
    if not colored.empty:
        colored.plot(
            ax=axis,
            column="walk_time_minutes",
            cmap="RdYlGn_r",
            norm=Normalize(0, 15),
            linewidth=0.1,
            edgecolor="#374151",
            alpha=0.88,
            zorder=3,
        )
    no_access = joined_3857[residential & ~joined_3857["within_15"]]
    if not no_access.empty:
        no_access.plot(
            ax=axis,
            facecolor="#9ca3af",
            edgecolor="#6b7280",
            linewidth=0.1,
            alpha=0.55,
            zorder=2.5,
        )

    aed_ids = set(access["nearest_aed_id"].dropna())
    aed_locations = {
        row["aed_id"]: row
        for row in _accepted_aeds(connection)
        if row["aed_id"] in aed_ids
    }
    if aed_locations:
        aed_frame = gpd.GeoDataFrame(
            list(aed_locations.values()),
            geometry=gpd.points_from_xy(
                [row["longitude"] for row in aed_locations.values()],
                [row["latitude"] for row in aed_locations.values()],
            ),
            crs="EPSG:4326",
        ).to_crs("EPSG:3857")
        aed_frame.plot(
            ax=axis,
            color="#111827",
            edgecolor="white",
            linewidth=0.5,
            markersize=22,
            zorder=5,
        )

    sm = plt.cm.ScalarMappable(norm=Normalize(0, 15), cmap="RdYlGn_r")
    sm.set_array([])
    colorbar = figure.colorbar(sm, ax=axis, shrink=0.72, pad=0.02)
    colorbar.set_label("Walking time to nearest AED (minutes)")
    axis.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#111827",
                markeredgecolor="white",
                markersize=7,
                label="AED",
            ),
            Line2D(
                [0],
                [0],
                marker="s",
                color="#9ca3af",
                markersize=7,
                label="Residential: no access within 15 minutes",
            ),
        ],
        loc="lower left",
        frameon=True,
        framealpha=0.92,
    )
    axis.set_title(f"AED walking access by building: {city_name}", fontsize=16)
    axis.set_axis_off()
    figure.text(
        0.01,
        0.01,
        "Residential population allocated with Tobler area interpolation; "
        f"footprints: {building_source}; walking network: OSM/Geofabrik",
        fontsize=7,
        color="#444444",
    )
    figure.tight_layout(pad=0.5)
    figure.savefig(output_path, format="png", bbox_inches="tight")
    plt.close(figure)

    if export_path:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        joined.to_file(export_path, layer="leon_buildings", driver="GPKG")

    return LeonMapStats(
        buildings=len(joined),
        residential_buildings=int(residential.sum()),
        estimated_population=float(joined["estimated_population"].sum()),
        population_5_minutes=float(
            joined.loc[
                joined["access_5_minutes"].fillna(False), "estimated_population"
            ].sum()
        ),
        population_10_minutes=float(
            joined.loc[
                joined["access_10_minutes"].fillna(False), "estimated_population"
            ].sum()
        ),
        population_15_minutes=float(
            joined.loc[
                joined["access_15_minutes"].fillna(False), "estimated_population"
            ].sum()
        ),
        mapped_aeds=len(aed_locations),
    )


def main() -> None:
    """Create the detailed León cadastral access map."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--buildings",
        type=Path,
        default=Path(
            "data/raw/catastro_buildings/footprints/24900/"
            "A.ES.SDGC.BU.24900.building.gml"
        ),
    )
    parser.add_argument("--municipality-id", default="24089")
    parser.add_argument("--city-name", default="León")
    parser.add_argument("--building-source", default="Spanish Cadastre INSPIRE BU")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/figures/leon_building_aed_access.png"),
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=Path("data/processed/leon_building_aed_access.gpkg"),
    )
    parser.add_argument("--no-basemap", action="store_true")
    args = parser.parse_args()
    with duckdb.connect(str(args.database), read_only=True) as connection:
        stats = create_leon_building_map(
            connection,
            args.buildings,
            args.output,
            args.export,
            not args.no_basemap,
            args.municipality_id,
            args.city_name,
            args.building_source,
        )
    print(stats)


if __name__ == "__main__":
    main()
