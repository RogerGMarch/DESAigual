"""Extract and persist the Castilla y León regional boundary."""

import argparse
from pathlib import Path

from pyrosm import OSM


def extract_castilla_y_leon_boundary(pbf_path: Path, output_path: Path) -> Path:
    """Extract the administrative level-4 region boundary from an OSM PBF."""
    if not pbf_path.exists():
        raise FileNotFoundError(pbf_path)
    osm = OSM(str(pbf_path), engine="out_of_core", workers=1)
    boundaries = osm.get_boundaries(name="Castilla y León")
    boundaries = boundaries[boundaries["admin_level"].astype(str) == "4"]
    if boundaries.empty:
        raise ValueError("Castilla y León administrative boundary was not found")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    boundaries.to_file(output_path, layer="castilla_y_leon", driver="GPKG")
    return output_path


def main() -> None:
    """Extract the regional boundary used for map masking."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pbf", type=Path, default=Path("data/raw/castilla-y-leon-latest.osm.pbf")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/interim/castilla_y_leon_boundary.gpkg"),
    )
    args = parser.parse_args()
    print(extract_castilla_y_leon_boundary(args.pbf, args.output))


if __name__ == "__main__":
    main()
