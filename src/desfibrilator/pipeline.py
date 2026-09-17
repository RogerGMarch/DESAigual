"""Command-line entry point for the baseline data pipeline."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import duckdb

from desfibrilator.config import ProjectConfig
from desfibrilator.geocode import (
    apply_manual_review,
    geocode_all_pending,
    geocode_mapbox_all_pending,
    geocode_nominatim_all_pending,
    import_filled_review,
    invalidate_cartociudad_cache,
    write_geocode_audit,
)
from desfibrilator.ingest import ingest_aeds, ingest_municipalities
from desfibrilator.schema import create_schema, insert_pipeline_run, table_counts


def main() -> None:
    """Run the configured ingestion pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/sources.yaml"))
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="create the DuckDB schema without requiring source files",
    )
    parser.add_argument(
        "--skip-geocoding",
        action="store_true",
        help="ingest tabular sources without making geocoder requests",
    )
    parser.add_argument(
        "--geocode-batch-size",
        type=int,
        default=None,
        help="maximum addresses per CartoCiudad request batch",
    )
    parser.add_argument(
        "--refresh-cartociudad",
        action="store_true",
        help="invalidate stale CartoCiudad selections before geocoding",
    )
    parser.add_argument(
        "--skip-cartociudad",
        action="store_true",
        help="run only the configured fallback geocoder",
    )
    parser.add_argument(
        "--skip-fallback",
        action="store_true",
        help="do not run the configured fallback geocoder",
    )
    parser.add_argument(
        "--retry-nominatim-rejected",
        action="store_true",
        help="retry previously rejected Nominatim addresses",
    )
    parser.add_argument(
        "--use-mapbox",
        action="store_true",
        help="enable Mapbox for unresolved addresses",
    )
    parser.add_argument(
        "--retry-mapbox-rejected",
        action="store_true",
        help="retry previously rejected Mapbox addresses",
    )
    parser.add_argument(
        "--apply-manual-review",
        action="store_true",
        help="apply accepted rows from data/interim/aed_manual_review.csv",
    )
    parser.add_argument(
        "--import-filled-review",
        action="store_true",
        help="import data/interim/aed_manual_review_filled.csv",
    )
    args = parser.parse_args()
    config = ProjectConfig.from_yaml(args.config)
    config.database_path.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(config.database_path)) as connection:
        create_schema(connection)
        if args.init_only:
            print(json.dumps(table_counts(connection), indent=2))
            return

        aed_path = _source_path(config, "aed")
        municipality_path = _source_path(config, "municipalities")
        missing = [
            str(path) for path in (aed_path, municipality_path) if not path.exists()
        ]
        if missing:
            raise FileNotFoundError(
                "Missing mandatory source files:\n" + "\n".join(missing)
            )

        run_id = _run_id(config)
        manifest = {
            name: {key: str(value) for key, value in source.items()}
            for name, source in config.sources.items()
        }
        try:
            ingest_aeds(connection, aed_path)
            ingest_municipalities(connection, municipality_path)
            if config.geocoding.get("enabled", True) and not args.skip_geocoding:
                if not args.skip_cartociudad:
                    if args.refresh_cartociudad:
                        invalidate_cartociudad_cache(connection)
                    geocode_all_pending(
                        connection,
                        config.geocoding["endpoint"],
                        timeout_seconds=config.geocoding.get("timeout_seconds", 30),
                        callback_parameter=config.geocoding.get(
                            "callback_parameter", "callback"
                        ),
                        delay_seconds=config.geocoding.get("delay_seconds", 0.2),
                        batch_size=args.geocode_batch_size
                        or config.geocoding.get("batch_size", 250),
                    )
                fallback = config.geocoding.get("fallback", {})
                if fallback.get("enabled", False) and not args.skip_fallback:
                    geocode_nominatim_all_pending(
                        connection,
                        fallback["endpoint"],
                        _municipality_bounds(connection),
                        fallback["user_agent"],
                        timeout_seconds=fallback.get("timeout_seconds", 30),
                        delay_seconds=fallback.get("delay_seconds", 1.0),
                        batch_size=fallback.get("batch_size", 250),
                        retry_rejected=args.retry_nominatim_rejected,
                    )
                mapbox = config.geocoding.get("mapbox", {})
                if mapbox.get("enabled", False) or args.use_mapbox:
                    geocode_mapbox_all_pending(
                        connection,
                        mapbox["endpoint"],
                        os.environ.get("MAPBOX_ACCESS_TOKEN", ""),
                        _municipality_bounds(connection),
                        timeout_seconds=mapbox.get("timeout_seconds", 60),
                        batch_size=mapbox.get("batch_size", 100),
                        permanent=mapbox.get("permanent", True),
                        retry_rejected=args.retry_mapbox_rejected,
                        municipality_centers=_municipality_centers(connection),
                        proximity_radius_km=mapbox.get("proximity_radius_km", 35),
                    )
            if args.apply_manual_review:
                apply_manual_review(
                    connection,
                    config.root / "data/interim/aed_manual_review.csv",
                )
            if args.import_filled_review:
                import_filled_review(
                    connection,
                    config.root / "data/interim/aed_manual_review_filled.csv",
                )
            write_geocode_audit(
                connection,
                config.root / "reports/aed_geocode_audit.csv",
            )
            insert_pipeline_run(connection, run_id, "success", manifest)
        except Exception as error:
            insert_pipeline_run(connection, run_id, "failed", manifest, str(error))
            raise

        print(json.dumps(table_counts(connection), indent=2))


def _source_path(config: ProjectConfig, name: str) -> Path:
    try:
        return Path(config.sources[name]["path"])
    except KeyError as error:
        raise KeyError(f"Missing source configuration for {name!r}") from error


def _run_id(config: ProjectConfig) -> str:
    """Create a deterministic run identifier from configured source paths."""
    manifest = json.dumps(
        {name: str(source) for name, source in config.sources.items()},
        sort_keys=True,
    )
    return hashlib.sha256(manifest.encode()).hexdigest()[:16]


def _municipality_bounds(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[float, float, float, float]:
    """Return the municipality extent as west, south, east, north."""
    west, south, east, north = connection.sql(
        """
        SELECT min(longitude), min(latitude), max(longitude), max(latitude)
        FROM municipalities
        WHERE longitude IS NOT NULL AND latitude IS NOT NULL
        """
    ).fetchone()
    if None in (west, south, east, north):
        raise ValueError("Municipality coordinates are required for bounded fallback")
    return west, south, east, north


def _municipality_centers(
    connection: duckdb.DuckDBPyConnection,
) -> dict[str, tuple[float, float]]:
    """Return municipality center points keyed by normalized municipality name."""
    from desfibrilator.normalize import municipality_key

    return {
        municipality_key(name): (latitude, longitude)
        for name, latitude, longitude in connection.sql(
            "SELECT municipio, latitude, longitude FROM municipalities"
        ).fetchall()
        if name and latitude is not None and longitude is not None
    }


if __name__ == "__main__":
    main()
