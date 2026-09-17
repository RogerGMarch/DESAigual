"""Create a static AED map from the DuckDB geocode cache."""

import argparse
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import duckdb
import httpx
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.image import imread
from pyproj import Transformer

from desfibrilator.normalize import address_key, normalized_key


@dataclass(frozen=True)
class MapStats:
    """Counts describing the records included in an AED map."""

    total_aeds: int
    mapped_aeds: int

    @property
    def unmapped_aeds(self) -> int:
        """Return the number of AEDs without valid coordinates."""
        return self.total_aeds - self.mapped_aeds


def create_aed_map(
    connection: duckdb.DuckDBPyConnection,
    output_path: Path,
) -> MapStats:
    """Render geocoded AEDs on the official IGN basemap as a PNG.

    Args:
        connection: Open DuckDB connection containing canonical tables.
        output_path: Destination for the generated PNG map.

    Returns:
        Counts of total and successfully mapped AED records.
    """
    aeds = connection.sql(
        """
        SELECT aed_id, address, municipality, province
        FROM aed_locations
        """
    ).fetchall()
    geocodes = {
        row[0]: row[1:]
        for row in connection.sql(
            """
            SELECT address_key, latitude, longitude, geocode_confidence,
                   matched_address, provider, match_precision, match_status,
                   response_json
            FROM aed_geocodes
            """
        ).fetchall()
    }
    municipality_bounds = connection.sql(
        """
        SELECT min(longitude), min(latitude), max(longitude), max(latitude)
        FROM municipalities
        WHERE longitude IS NOT NULL AND latitude IS NOT NULL
        """
    ).fetchone()

    points = []
    for aed_id, address, municipality, province in aeds:
        if not address:
            continue
        geocode = geocodes.get(address_key(address, municipality, province))
        if geocode is None or not _valid_coordinates(geocode[0], geocode[1]):
            continue
        if (
            municipality_bounds[0] is not None
            and not geocode[6].startswith("accepted_manual")
            and not _within_region(geocode[0], geocode[1], municipality_bounds)
        ):
            continue
        if geocode[6] is not None and not geocode[6].startswith("accepted"):
            continue
        if not _is_expected_match(geocode[7], municipality, province):
            continue
        points.append((aed_id, address, municipality, province, geocode))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    longitudes = [point[4][1] for point in points]
    latitudes = [point[4][0] for point in points]
    x_values, y_values = transformer.transform(longitudes, latitudes)

    figure, axis = plt.subplots(figsize=(12, 10), dpi=180)
    if points:
        exact_points = [point for point in points if _precision(point) == "exact"]
        site_points = [
            point for point in points if _precision(point) in ("facility", "site")
        ]
        street_points = [point for point in points if _precision(point) == "street"]
        if exact_points:
            exact_x, exact_y = _project_points(exact_points, transformer)
            axis.scatter(
                exact_x,
                exact_y,
                s=12,
                c="#b91c1c",
                marker="o",
                alpha=0.8,
                linewidths=0.25,
                edgecolors="white",
                label="Exact address",
                zorder=2,
            )
        if street_points:
            street_x, street_y = _project_points(street_points, transformer)
            axis.scatter(
                street_x,
                street_y,
                s=18,
                c="#d97706",
                marker="^",
                alpha=0.85,
                linewidths=0.25,
                edgecolors="white",
                label="Street-level match",
                zorder=3,
            )
        if site_points:
            site_x, site_y = _project_points(site_points, transformer)
            axis.scatter(
                site_x,
                site_y,
                s=24,
                c="#7c3aed",
                marker="s",
                alpha=0.85,
                linewidths=0.25,
                edgecolors="white",
                label="Facility/site match",
                zorder=4,
            )
        _set_extent(axis, x_values, y_values)
        _add_ign_basemap(axis)
        axis.legend(loc="lower left", frameon=True, framealpha=0.9)
    axis.set_title("Registered AED locations in Castilla y Leon", fontsize=16)
    axis.set_axis_off()
    figure.text(
        0.01,
        0.01,
        "Basemap: IGN Mapa Base, CC BY 4.0 (scne.es) | "
        "Geocoding: Nominatim/Mapbox; OpenStreetMap contributors, ODbL "
        "where applicable",
        fontsize=7,
        color="#444444",
    )
    figure.tight_layout(pad=0.5)
    figure.savefig(output_path, format="png", bbox_inches="tight")
    plt.close(figure)
    return MapStats(total_aeds=len(aeds), mapped_aeds=len(points))


def _project_points(points: list[tuple], transformer: Transformer):
    """Project point records from WGS84 to Web Mercator."""
    longitudes = [point[4][1] for point in points]
    latitudes = [point[4][0] for point in points]
    return transformer.transform(longitudes, latitudes)


def _precision(point: tuple) -> str:
    """Infer precision for legacy cache rows without metadata."""
    precision = point[4][5]
    if precision:
        return precision
    response = point[4][7]
    if isinstance(response, str):
        response = json.loads(response)
    return "exact" if response.get("type") == "portal" else "street"


def _valid_coordinates(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def _within_region(latitude: float, longitude: float, bounds: tuple) -> bool:
    """Reject geocoder candidates that fall clearly outside Castilla y Leon."""
    min_longitude, min_latitude, max_longitude, max_latitude = bounds
    margin = 0.25
    return (
        min_longitude - margin <= longitude <= max_longitude + margin
        and min_latitude - margin <= latitude <= max_latitude + margin
    )


def _is_expected_match(
    response: str | dict | None,
    municipality: str | None,
    province: str | None,
) -> bool:
    """Accept only matches for the source locality and province."""
    if not response or response == "{}":
        return True
    if isinstance(response, str):
        response = json.loads(response)
    code = response.get("comunidadAutonomaCode")
    if code is not None and code != "07":
        return False
    matched_province = response.get("province")
    if matched_province and province:
        if normalized_key(matched_province) != normalized_key(province):
            return False
    matched_municipality = response.get("muni")
    if matched_municipality and municipality:
        if _municipality_key(matched_municipality) != _municipality_key(municipality):
            return False
    return True


def _municipality_key(value: str) -> str:
    """Normalize Spanish municipality names, including trailing articles."""
    key = normalized_key(value)
    for article in ("el", "la", "los", "las"):
        suffix = f"_{article}"
        if key.endswith(suffix):
            return f"{article}_{key[: -len(suffix)]}"
    return key


def _set_extent(axis, x_values, y_values) -> None:
    """Set a small geographic margin around the plotted points."""
    x_margin = max((max(x_values) - min(x_values)) * 0.04, 5_000)
    y_margin = max((max(y_values) - min(y_values)) * 0.04, 5_000)
    axis.set_xlim(min(x_values) - x_margin, max(x_values) + x_margin)
    axis.set_ylim(min(y_values) - y_margin, max(y_values) + y_margin)


def _add_ign_basemap(axis) -> None:
    """Fetch one official IGN WMS image for the current map extent."""
    x_min, x_max = axis.get_xlim()
    y_min, y_max = axis.get_ylim()
    response = httpx.get(
        "https://www.ign.es/wms-inspire/ign-base",
        params={
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetMap",
            "LAYERS": "IGNBaseTodo-nofondo",
            "STYLES": "default",
            "CRS": "EPSG:3857",
            "BBOX": f"{x_min},{y_min},{x_max},{y_max}",
            "WIDTH": 1800,
            "HEIGHT": 1500,
            "FORMAT": "image/png",
            "TRANSPARENT": "FALSE",
        },
        headers={"User-Agent": "desfibrilator-urban-network/0.1"},
        timeout=60,
    )
    response.raise_for_status()
    image = imread(BytesIO(response.content), format="png")
    axis.imshow(
        image,
        extent=(x_min, x_max, y_min, y_max),
        origin="upper",
        zorder=0,
    )
    axis.set_xlim(x_min, x_max)
    axis.set_ylim(y_min, y_max)


def main() -> None:
    """Generate the configured static AED map."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/processed/urban_network.duckdb"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/aed_map.png"),
    )
    args = parser.parse_args()

    with duckdb.connect(str(args.database), read_only=True) as connection:
        stats = create_aed_map(connection, args.output)
    print(
        f"Wrote {args.output}: {stats.mapped_aeds}/{stats.total_aeds} AEDs mapped; "
        f"{stats.unmapped_aeds} unmapped"
    )


if __name__ == "__main__":
    main()
