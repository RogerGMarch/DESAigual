"""Analyze municipality size and modeled access for the editorial storyboard."""

import argparse
import json
from pathlib import Path

BANDS = (
    (0, 100, "Menos de 100"),
    (100, 500, "100–499"),
    (500, 2000, "500–1.999"),
    (2000, 10000, "2.000–9.999"),
    (10000, 50000, "10.000–49.999"),
    (50000, float("inf"), "50.000 o más"),
)


def analyze(features):
    """Separate complete population counts from available-only access estimates."""
    rows = [feature["properties"] for feature in features]
    total = sum(row["population"] for row in rows)
    groups = []
    for low, high, label in BANDS:
        members = [row for row in rows if low <= row["population"] < high]
        valid = [row for row in members if row["status"] == "available"]
        population = sum(row["population"] for row in members)
        modeled = sum(row["population"] for row in valid)
        groups.append(
            {
                "label": label,
                "municipalities": len(members),
                "population": population,
                "municipalityShare": len(members) / len(rows) * 100,
                "populationShare": population / total * 100,
                "availableMunicipalities": len(valid),
                "modeledPopulation": modeled,
                "modeledPopulationShare": modeled / population * 100
                if population
                else None,
                "coverage5": sum(row["population"] * row["coverage5"] for row in valid)
                / modeled
                if modeled
                else None,
            }
        )
    return {
        "municipalities": len(rows),
        "population": total,
        "groups": groups,
        "method": "Population distribution uses every exported municipality. Access "
        "uses available municipalities only, weighted by official population; "
        "missing or review results are never zero-filled.",
        "source": "web/public/data/municipalities.geojson",
    }


def render(result, output):
    """Draw population distribution and access comparisons with their denominators."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups = result["groups"]
    small_towns = f"{sum(g['municipalityShare'] for g in groups[:2]):.1f}".replace(
        ".", ","
    )
    small_people = f"{sum(g['populationShare'] for g in groups[:2]):.1f}".replace(
        ".", ","
    )
    count = f"{result['municipalities']:,}".replace(",", ".")
    population = f"{result['population']:,}".replace(",", ".")
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), dpi=180, sharey=True)
    fig.text(
        0.04,
        0.94,
        "Muchos municipios pequeños. La población se concentra.",
        fontsize=21,
        color="#252525",
    )
    fig.text(
        0.04,
        0.885,
        f"El {small_towns}% tiene menos de 500 habitantes; "
        f"reúne el {small_people}% de la población.",
        fontsize=13,
        color="#666666",
    )
    for ax, field, title, color in zip(
        axes,
        ["municipalityShare", "populationShare"],
        ["Porcentaje de municipios", "Porcentaje de población"],
        ["#418b80", "#b34f40"],
        strict=True,
    ):
        values = [g[field] for g in groups]
        ax.barh(range(6), values, height=0.5, color=color)
        ax.set_title(title, loc="left", fontsize=13, pad=20, color="#444444")
        ax.set_xlim(0, 55)
        ax.set_xticks([0, 25, 50], ["0%", "25%", "50%"])
        ax.set_yticks(range(6), [g["label"] for g in groups])
        ax.tick_params(axis="both", length=0, colors="#666666", labelsize=11)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#eeeeee")
        for y, value in enumerate(values):
            ax.text(
                value + 0.8,
                y,
                f"{value:.1f}%".replace(".", ","),
                va="center",
                fontsize=11,
                color="#333333",
            )
        for spine in ax.spines.values():
            spine.set_visible(False)
    axes[0].invert_yaxis()
    fig.text(
        0.04,
        0.07,
        f"Habitantes por municipio · {count} municipios · {population} habitantes",
        fontsize=11,
        color="#666666",
    )
    fig.text(
        0.04,
        0.025,
        "Fuente: población municipal del proyecto. "
        "Incluye municipios sin resultados de acceso.",
        fontsize=10,
        color="#777777",
    )
    fig.subplots_adjust(left=0.18, right=0.97, top=0.76, bottom=0.16, wspace=0.25)
    fig.savefig(output / "population-distribution.png", facecolor="white")
    plt.close(fig)


def main():
    """Export a reproducible analysis and storyboard chart."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("web/public/data/municipalities.geojson")
    )
    parser.add_argument("--output", type=Path, default=Path("web/editorial"))
    args = parser.parse_args()
    result = analyze(json.loads(args.input.read_text())["features"])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "municipality-analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    render(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
