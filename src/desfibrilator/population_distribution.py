"""Plot the population-weighted distribution of walking time to an AED."""

import argparse
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def render_population_proximity_distribution(
    connection: duckdb.DuckDBPyConnection,
    output_path: Path,
    csv_path: Path | None = None,
) -> dict[str, float | int]:
    """Render resident distribution and cumulative access to the nearest AED.

    Population is the weight, so a large building contributes more than a
    small building. Missing walking times are reported as residents not
    reached within the configured search window.
    """
    data = connection.sql(
        """
        SELECT walk_time_minutes, estimated_population
        FROM building_aed_access
        WHERE estimated_population > 0
        """
    ).df()
    if data.empty:
        raise ValueError("building_aed_access has no population records")
    data["estimated_population"] = data["estimated_population"].astype(float)
    total_population = float(data["estimated_population"].sum())
    routed = data.dropna(subset=["walk_time_minutes"]).copy()
    routed = routed.sort_values("walk_time_minutes")
    routed_population = float(routed["estimated_population"].sum())
    if routed_population <= total_population / 2:
        raise ValueError(
            "The population-weighted median is censored because fewer than half "
            "of residents have a known walking time"
        )
    routed["cumulative_population"] = routed["estimated_population"].cumsum()
    median_row = routed[routed["cumulative_population"] >= total_population / 2].iloc[0]
    median_minutes = float(median_row["walk_time_minutes"])

    bin_edges = [*range(0, 16), 20, 30, 45, 60, 90, 120, 180, 240, 300, 360]
    bin_labels = [
        *[f"{value}-{value + 1}" for value in range(15)],
        "15-20",
        "20-30",
        "30-45",
        "45-60",
        "60-90",
        "90-120",
        "120-180",
        "180-240",
        "240-300",
        "300-360",
    ]
    bins = pd.cut(
        routed["walk_time_minutes"],
        bins=bin_edges,
        right=False,
        labels=bin_labels,
    )
    histogram = (
        routed.assign(time_bin=bins)
        .groupby("time_bin", observed=False)["estimated_population"]
        .sum()
        .reindex(bin_labels, fill_value=0)
        .rename("population")
        .reset_index()
    )
    histogram.loc[len(histogram)] = [
        ">360 / no route",
        total_population - routed_population,
    ]
    histogram["share_percent"] = 100 * histogram["population"] / total_population
    histogram["cumulative_percent"] = histogram["share_percent"].cumsum()
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        histogram.to_csv(csv_path, index=False)

    figure, axes = plt.subplots(1, 2, figsize=(15, 6), dpi=200)
    colors = ["#166534"] * len(bin_labels) + ["#9ca3af"]
    axes[0].bar(
        histogram["time_bin"],
        histogram["share_percent"],
        color=colors,
        edgecolor="white",
        linewidth=0.35,
    )
    axes[0].axvline(
        median_minutes + 0.5,
        color="#b91c1c",
        linestyle="--",
        linewidth=1.5,
        label=f"Weighted median: {median_minutes:.1f} min",
    )
    axes[0].set_xlabel("Walking time to nearest AED (minutes)")
    axes[0].set_ylabel("Estimated residents (%)")
    axes[0].set_title("Residents by AED proximity")
    axes[0].tick_params(axis="x", rotation=65, labelsize=7)
    axes[0].legend(loc="upper right")
    axes[0].grid(axis="y", color="#d1d5db", linewidth=0.6)

    cumulative = routed.groupby("walk_time_minutes", as_index=False)[
        "estimated_population"
    ].sum()
    cumulative["share_percent"] = (
        100 * cumulative["estimated_population"].cumsum() / total_population
    )
    axes[1].step(
        cumulative["walk_time_minutes"],
        cumulative["share_percent"],
        where="post",
        color="#166534",
        linewidth=1.8,
        label="Cumulative residents",
    )
    axes[1].axhline(50, color="#b91c1c", linestyle="--", linewidth=1)
    axes[1].axvline(
        median_minutes,
        color="#b91c1c",
        linestyle="--",
        linewidth=1.5,
        label=f"Median: {median_minutes:.1f} min",
    )
    axes[1].axvline(15, color="#6b7280", linestyle=":", linewidth=1)
    axes[1].set_xlim(0, max(60, float(cumulative["walk_time_minutes"].max())))
    axes[1].set_ylim(0, 100)
    axes[1].set_xlabel("Walking time to nearest AED (minutes)")
    axes[1].set_ylabel("Cumulative estimated residents (%)")
    axes[1].set_title("Cumulative population access")
    axes[1].legend(loc="lower right")
    axes[1].grid(color="#d1d5db", linewidth=0.6)

    within_15 = (
        100
        * routed.loc[routed["walk_time_minutes"] <= 15, "estimated_population"].sum()
        / total_population
    )
    figure.suptitle("Population-weighted AED proximity distribution", fontsize=16)
    figure.text(
        0.01,
        0.01,
        f"Weighted median: {median_minutes:.1f} minutes; "
        f"within 15 minutes: {within_15:.1f}%; "
        "gray = not reached within the 360-minute search window",
        fontsize=8,
        color="#4b5563",
    )
    figure.tight_layout(rect=(0, 0.05, 1, 0.95))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, format="png", bbox_inches="tight")
    plt.close(figure)
    return {
        "municipalities": int(
            connection.sql(
                "SELECT count(*) FROM municipality_population_access"
            ).fetchone()[0]
        ),
        "population": total_population,
        "median_minutes": median_minutes,
        "within_15_percent": within_15,
    }


def main() -> None:
    """Create the population-weighted AED proximity distribution plot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/figures/population_aed_proximity_distribution.png"),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("reports/population_aed_proximity_distribution.csv"),
    )
    args = parser.parse_args()
    with duckdb.connect(str(args.database), read_only=True) as connection:
        stats = render_population_proximity_distribution(
            connection, args.output, args.csv
        )
    print(stats)


if __name__ == "__main__":
    main()
