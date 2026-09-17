"""Plot municipality population coverage by walking-time threshold."""

import argparse
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

THRESHOLDS = (5, 10, 15)


def render_municipality_access_plot(
    connection: duckdb.DuckDBPyConnection,
    output_path: Path,
    csv_path: Path | None = None,
) -> pd.DataFrame:
    """Render coverage lines for all municipalities with building estimates.

    Municipalities are ordered from largest to smallest interpolated
    population. The returned table contains the plotted percentages.
    """
    data = connection.sql(
        """
        SELECT municipality_id, municipality_name, population_total,
               population_5_minutes, population_10_minutes,
               population_15_minutes, buildings_total,
               buildings_with_population
        FROM municipality_population_access
        WHERE population_total > 0
        ORDER BY population_total DESC, municipality_id
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
    data.insert(0, "population_rank", range(1, len(data) + 1))
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(csv_path, index=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(13, 7), dpi=200)
    rank = data["population_rank"]
    styles = {
        5: ("#b91c1c", "5 minutes"),
        10: ("#d97706", "10 minutes"),
        15: ("#15803d", "15 minutes"),
    }
    for threshold, (color, label) in styles.items():
        coverage = data[f"coverage_{threshold}_minutes"]
        axis.plot(
            rank,
            coverage,
            color=color,
            linewidth=0.35,
            alpha=0.18,
        )
        axis.plot(
            rank,
            coverage.rolling(51, center=True, min_periods=1).mean(),
            color=color,
            linewidth=1.8,
            label=label,
        )
    axis.set_xlim(1, len(data))
    axis.set_ylim(0, 100)
    axis.set_xlabel("Municipalities ranked by interpolated population")
    axis.set_ylabel("Estimated population with AED access (%)")
    axis.set_title("Municipality population access to AEDs by walking time")
    axis.grid(axis="y", color="#d1d5db", linewidth=0.6, alpha=0.8)
    axis.legend(title="Walking threshold", loc="lower right")
    weighted = {
        threshold: 100
        * data[f"population_{threshold}_minutes"].sum()
        / data["population_total"].sum()
        for threshold in THRESHOLDS
    }
    note = (
        f"n={len(data):,} municipalities with valid building estimates; "
        "population-weighted coverage: "
        f"5 min {weighted[5]:.1f}%, 10 min {weighted[10]:.1f}%, "
        f"15 min {weighted[15]:.1f}%"
    )
    figure.text(0.01, 0.01, note, fontsize=8, color="#4b5563")
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    figure.savefig(output_path, format="png", bbox_inches="tight")
    plt.close(figure)
    return data


def main() -> None:
    """Create the municipality accessibility line plot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/figures/municipality_population_access.png"),
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("reports/municipality_population_access.csv"),
    )
    args = parser.parse_args()
    with duckdb.connect(str(args.database), read_only=True) as connection:
        data = render_municipality_access_plot(connection, args.output, args.csv)
    print(f"Wrote {args.output} for {len(data)} municipalities")
    print(f"Wrote {args.csv}")


if __name__ == "__main__":
    main()
