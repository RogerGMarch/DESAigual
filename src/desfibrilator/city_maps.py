"""Create cadastral AED-access maps for the largest municipalities."""

import argparse
from pathlib import Path

import duckdb
from tqdm import tqdm

from desfibrilator.leon_map import create_leon_building_map

MAJOR_CITIES = (
    ("47186", "47900", "Valladolid"),
    ("09059", "09900", "Burgos"),
    ("37274", "37900", "Salamanca"),
    ("24089", "24900", "León"),
    ("34120", "34900", "Palencia"),
    ("24115", "24118", "Ponferrada"),
    ("49275", "49900", "Zamora"),
    ("05019", "05900", "Ávila"),
    ("40194", "40900", "Segovia"),
    ("42173", "42900", "Soria"),
)


def create_major_city_maps(
    connection: duckdb.DuckDBPyConnection,
    footprint_root: Path,
    output_root: Path,
    export_root: Path,
    add_basemap: bool = True,
) -> list[str]:
    """Create maps for cities with valid cadastral footprint files."""
    created = []
    for municipality_id, cadastral_code, city_name in tqdm(
        MAJOR_CITIES, desc="Creating major-city maps", unit="city"
    ):
        building_path = (
            footprint_root
            / cadastral_code
            / f"A.ES.SDGC.BU.{cadastral_code}.building.gml"
        )
        if not building_path.exists() or building_path.stat().st_size < 1000:
            print(f"Skipping {city_name}: cadastral footprint unavailable")
            continue
        slug = city_name.lower().replace("á", "a").replace("é", "e").replace("ó", "o")
        slug = slug.replace(" ", "_")
        output = output_root / f"{slug}_building_aed_access.png"
        export = export_root / f"{slug}_building_aed_access.gpkg"
        create_leon_building_map(
            connection,
            building_path,
            output,
            export,
            add_basemap,
            municipality_id,
            city_name,
        )
        created.append(city_name)
    return created


def main() -> None:
    """Create building maps for the largest municipalities."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument(
        "--footprints",
        type=Path,
        default=Path("data/raw/catastro_buildings/footprints"),
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("reports/figures/cities")
    )
    parser.add_argument(
        "--export-root", type=Path, default=Path("data/processed/city_buildings")
    )
    parser.add_argument("--no-basemap", action="store_true")
    args = parser.parse_args()
    with duckdb.connect(str(args.database), read_only=True) as connection:
        created = create_major_city_maps(
            connection,
            args.footprints,
            args.output_root,
            args.export_root,
            not args.no_basemap,
        )
    print(f"Created {len(created)} city maps: {', '.join(created)}")


if __name__ == "__main__":
    main()
