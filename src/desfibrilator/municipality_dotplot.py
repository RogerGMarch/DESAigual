"""Plot municipality AED coverage distributions with median markers."""

import argparse
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

THRESHOLDS = (5, 10, 15)
COLORS = {5: "#b91c1c", 10: "#d97706", 15: "#15803d"}


def municipality_coverage_table(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    """Return municipality coverage percentages and population weights."""
    data = connection.sql(
        """
        SELECT municipality_id, municipality_name, population_total,
               population_5_minutes, population_10_minutes,
               population_15_minutes
        FROM municipality_population_access
        WHERE population_total > 0
        ORDER BY municipality_id
        """
    ).df()
    if data.empty:
        raise ValueError(
            "municipality_population_access is empty; run population access first"
        )
    for threshold in THRESHOLDS:
        data[f"coverage_{threshold}_minutes"] = (
            100 * data[f"population_{threshold}_minutes"] / data["population_total"]
        ).clip(0, 100)
    return data


def weighted_median(values: pd.Series, weights: pd.Series) -> float:
    """Return a weighted median for non-negative values and weights."""
    frame = pd.DataFrame({"value": values, "weight": weights}).sort_values("value")
    frame = frame[frame["weight"] > 0]
    cumulative = frame["weight"].cumsum()
    return float(frame.loc[cumulative >= frame["weight"].sum() / 2, "value"].iloc[0])


def render_municipality_dotplot(
    connection: duckdb.DuckDBPyConnection,
    output_path: Path,
    csv_path: Path | None = None,
) -> dict[str, float | int]:
    """Render one dot row per walking threshold for all municipalities."""
    data = municipality_coverage_table(connection)
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(csv_path, index=False)

    figure, axis = plt.subplots(figsize=(13, 6.5), dpi=220)
    rng = np.random.default_rng(42)
    medians = {}
    weighted_medians = {}
    for row, threshold in enumerate(THRESHOLDS):
        coverage = data[f"coverage_{threshold}_minutes"]
        population = data["population_total"]
        jitter = rng.uniform(-0.22, 0.22, len(data))
        sizes = 8 + 42 * np.sqrt(population / population.max())
        axis.scatter(
            coverage,
            row + jitter,
            s=sizes,
            color=COLORS[threshold],
            alpha=0.48,
            edgecolors="white",
            linewidths=0.25,
            label=f"{threshold}-minute access",
            zorder=3,
        )
        medians[threshold] = float(coverage.median())
        weighted_medians[threshold] = weighted_median(coverage, population)
        axis.vlines(
            medians[threshold],
            row - 0.34,
            row + 0.34,
            color=COLORS[threshold],
            linewidth=2.5,
            zorder=4,
        )
        axis.vlines(
            weighted_medians[threshold],
            row - 0.34,
            row + 0.34,
            color="#111827",
            linewidth=2,
            linestyle="--",
            zorder=5,
        )

    axis.set_xlim(0, 100)
    axis.set_ylim(-0.6, len(THRESHOLDS) - 0.4)
    axis.set_yticks(range(len(THRESHOLDS)), [f"{t} minutes" for t in THRESHOLDS])
    axis.set_xlabel("Estimated population with nearest AED access (%)")
    axis.set_title("Municipality AED population coverage distributions")
    axis.grid(axis="x", color="#d1d5db", linewidth=0.6)
    axis.legend(loc="lower right", frameon=True)
    axis.text(
        0.99,
        1.02,
        "Solid line: municipality median   Dashed line: population-weighted median",
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#4b5563",
    )
    figure.text(
        0.01,
        0.01,
        f"n={len(data):,} municipalities with valid building estimates; "
        "dot size is proportional to estimated municipality population",
        fontsize=8,
        color="#4b5563",
    )
    figure.tight_layout(rect=(0, 0.05, 1, 0.95))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, format="png", bbox_inches="tight")
    plt.close(figure)
    return {
        "municipalities": len(data),
        **{f"median_{t}_minutes": medians[t] for t in THRESHOLDS},
        **{f"weighted_median_{t}_minutes": weighted_medians[t] for t in THRESHOLDS},
    }


def main() -> None:
    """Create the municipality coverage dot plot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/figures/municipality_population_access_dotplot.png"),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("reports/municipality_population_access_dotplot.csv"),
    )
    args = parser.parse_args()
    with duckdb.connect(str(args.database), read_only=True) as connection:
        stats = render_municipality_dotplot(connection, args.output, args.csv)
    print(stats)


if __name__ == "__main__":
    main()
