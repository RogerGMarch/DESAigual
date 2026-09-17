"""DuckDB schema for the AED accessibility baseline."""

import json
from typing import Any

import duckdb

TABLES = (
    "municipalities",
    "aed_locations",
    "aed_geocodes",
    "aed_geocode_attempts",
    "llm_geocode_reviews",
    "hospitals",
    "road_nodes",
    "road_edges",
    "walk_nodes",
    "walk_edges",
    "node_hospital_access",
    "aed_hospital_access",
    "building_aed_access",
    "building_population",
    "municipality_population_access",
    "population_access_grid",
    "pipeline_runs",
)


def create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create the canonical tables if they do not already exist."""
    connection.sql(
        """
        CREATE TABLE IF NOT EXISTS municipalities (
            municipio VARCHAR,
            cod_municipio VARCHAR,
            cod_provincia VARCHAR,
            cod_ine VARCHAR,
            poblacion BIGINT,
            longitude DOUBLE,
            latitude DOUBLE,
            source_updated_at VARCHAR,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS aed_locations (
            aed_id VARCHAR,
            address VARCHAR,
            municipality VARCHAR,
            province VARCHAR,
            registration_date VARCHAR,
            organisation VARCHAR,
            source_updated_at VARCHAR,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS aed_geocodes (
            address_key VARCHAR PRIMARY KEY,
            address VARCHAR,
            municipality VARCHAR,
            province VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            geocode_confidence DOUBLE,
            matched_address VARCHAR,
            response_json JSON,
            geocoded_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS aed_geocode_attempts (
            address_key VARCHAR,
            provider VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            geocode_confidence DOUBLE,
            matched_address VARCHAR,
            match_precision VARCHAR,
            match_status VARCHAR,
            response_json JSON,
            attempted_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS llm_geocode_reviews (
            address_key VARCHAR PRIMARY KEY,
            model VARCHAR,
            prompt_version VARCHAR,
            input_hash VARCHAR,
            hypotheses_json JSON,
            candidates_json JSON,
            selected_candidate_id VARCHAR,
            review_status VARCHAR,
            review_confidence DOUBLE,
            review_reason VARCHAR,
            reviewed_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS hospitals (
            hospital_id VARCHAR PRIMARY KEY,
            name VARCHAR,
            municipality VARCHAR,
            province VARCHAR,
            address VARCHAR,
            longitude DOUBLE,
            latitude DOUBLE,
            emergency_capable BOOLEAN,
            source_updated_at VARCHAR,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS road_nodes (
            node_id BIGINT PRIMARY KEY,
            longitude DOUBLE,
            latitude DOUBLE,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS road_edges (
            edge_id VARCHAR,
            source_id BIGINT,
            target_id BIGINT,
            highway VARCHAR,
            name VARCHAR,
            length_m DOUBLE,
            maxspeed_kmh DOUBLE,
            travel_time_minutes DOUBLE,
            geometry_wkt VARCHAR,
            source_updated_at VARCHAR,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS walk_nodes (
            node_id BIGINT PRIMARY KEY,
            longitude DOUBLE,
            latitude DOUBLE,
            component_id BIGINT,
            component_size BIGINT,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS walk_edges (
            edge_id VARCHAR,
            source_id BIGINT,
            target_id BIGINT,
            length_m DOUBLE,
            travel_time_minutes DOUBLE,
            geometry_wkt VARCHAR,
            source_updated_at VARCHAR,
            ingested_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS node_hospital_access (
            node_id BIGINT PRIMARY KEY,
            hospital_id VARCHAR,
            network_time_minutes DOUBLE,
            access_status VARCHAR,
            calculated_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS aed_hospital_access (
            aed_id VARCHAR,
            node_id BIGINT,
            hospital_id VARCHAR,
            network_time_minutes DOUBLE,
            access_status VARCHAR,
            calculated_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS building_aed_access (
            building_id VARCHAR,
            municipality_id VARCHAR,
            estimated_population DOUBLE,
            walk_time_minutes DOUBLE,
            nearest_aed_id VARCHAR,
            access_5_minutes BOOLEAN,
            access_10_minutes BOOLEAN,
            access_15_minutes BOOLEAN,
            calculated_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS building_population (
            building_id VARCHAR,
            municipality_id VARCHAR,
            x DOUBLE,
            y DOUBLE,
            estimated_population DOUBLE,
            residential_use VARCHAR,
            building_source VARCHAR,
            calculated_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS municipality_population_access (
            municipality_id VARCHAR PRIMARY KEY,
            municipality_name VARCHAR,
            population_total DOUBLE,
            population_5_minutes DOUBLE,
            population_10_minutes DOUBLE,
            population_15_minutes DOUBLE,
            buildings_total BIGINT,
            buildings_with_population BIGINT,
            calculated_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS population_access_grid (
            cell_id VARCHAR PRIMARY KEY,
            x DOUBLE,
            y DOUBLE,
            cell_size_m DOUBLE,
            population_total DOUBLE,
            population_5_minutes DOUBLE,
            population_10_minutes DOUBLE,
            population_15_minutes DOUBLE,
            calculated_at TIMESTAMP DEFAULT current_timestamp
        );
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id VARCHAR,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            status VARCHAR,
            source_manifest JSON,
            error_message VARCHAR
        );
        """
    )
    connection.execute(
        "ALTER TABLE aed_geocodes ADD COLUMN IF NOT EXISTS provider VARCHAR"
    )
    connection.execute(
        "ALTER TABLE aed_geocodes ADD COLUMN IF NOT EXISTS match_precision VARCHAR"
    )
    connection.execute(
        "ALTER TABLE aed_geocodes ADD COLUMN IF NOT EXISTS match_status VARCHAR"
    )
    connection.execute(
        "ALTER TABLE road_edges ADD COLUMN IF NOT EXISTS travel_time_minutes DOUBLE"
    )
    _migrate_duplicate_safe_aed_access(connection)
    connection.execute(
        "ALTER TABLE building_population ADD COLUMN IF NOT EXISTS "
        "building_source VARCHAR"
    )
    connection.execute(
        "ALTER TABLE walk_nodes ADD COLUMN IF NOT EXISTS component_id BIGINT"
    )
    connection.execute(
        "ALTER TABLE walk_nodes ADD COLUMN IF NOT EXISTS component_size BIGINT"
    )
    connection.execute(
        "UPDATE building_population SET building_source = 'cadastre' "
        "WHERE building_source IS NULL"
    )
    connection.execute(
        """
        UPDATE aed_geocodes
        SET provider = coalesce(provider, 'cartociudad'),
            match_status = coalesce(
                match_status,
                CASE
                    WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                    THEN 'accepted'
                    ELSE 'unresolved'
                END
            )
        WHERE provider IS NULL OR match_status IS NULL
        """
    )


def table_counts(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Return row counts for all canonical tables."""
    return {
        table: connection.sql(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in TABLES
    }


def _migrate_duplicate_safe_aed_access(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """Replace the initial AED result table that incorrectly required unique IDs."""
    has_primary_key = connection.sql(
        """
        SELECT count(*)
        FROM duckdb_constraints()
        WHERE table_name = 'aed_hospital_access'
          AND constraint_type = 'PRIMARY KEY'
        """
    ).fetchone()[0]
    if not has_primary_key:
        return
    connection.execute(
        "ALTER TABLE aed_hospital_access RENAME TO aed_hospital_access_legacy"
    )
    connection.execute(
        """
        CREATE TABLE aed_hospital_access (
            aed_id VARCHAR,
            node_id BIGINT,
            hospital_id VARCHAR,
            network_time_minutes DOUBLE,
            access_status VARCHAR,
            calculated_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        INSERT INTO aed_hospital_access
            (aed_id, node_id, hospital_id, network_time_minutes, access_status,
             calculated_at)
        SELECT aed_id, node_id, hospital_id, network_time_minutes, access_status,
               calculated_at
        FROM aed_hospital_access_legacy
        """
    )
    connection.execute("DROP TABLE aed_hospital_access_legacy")


def insert_pipeline_run(
    connection: duckdb.DuckDBPyConnection,
    run_id: str,
    status: str,
    source_manifest: dict[str, Any],
    error_message: str | None = None,
) -> None:
    """Record one pipeline execution and its source manifest."""
    connection.execute(
        """
        INSERT INTO pipeline_runs
            (run_id, started_at, finished_at, status, source_manifest, error_message)
        VALUES (?, current_timestamp, current_timestamp, ?, ?::JSON, ?)
        """,
        [run_id, status, json.dumps(source_manifest), error_message],
    )
