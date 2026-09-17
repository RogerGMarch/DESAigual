"""Input readers and canonical table ingestion."""

import csv
import json
from pathlib import Path
from typing import Any

import duckdb

from desfibrilator.normalize import normalize_aed, normalize_municipality


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read a CSV or JSON source into a list of record dictionaries."""
    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
        if isinstance(payload, dict):
            for key in ("data", "results", "records"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if not isinstance(payload, list):
            raise ValueError(f"Expected a list of records in {path}")
        return payload

    text = _read_text(path)
    try:
        delimiter = csv.Sniffer().sniff(text[:4096], delimiters=",;").delimiter
    except csv.Error:
        delimiter = ","
    return list(csv.DictReader(text.splitlines(), delimiter=delimiter))


def _read_text(path: Path) -> str:
    """Read JCyL text files with UTF-8 or legacy encoding."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "iso-8859-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw, 0, 1, f"Could not decode {path}")


def ingest_municipalities(connection: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Replace canonical municipality rows with a normalized source file."""
    rows = [normalize_municipality(row) for row in read_records(path)]
    connection.execute("DELETE FROM municipalities")
    connection.executemany(
        """
        INSERT INTO municipalities
            (municipio, cod_municipio, cod_provincia, cod_ine, poblacion,
             longitude, latitude, source_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def ingest_aeds(connection: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Replace canonical AED rows with a normalized source file."""
    rows = [normalize_aed(row) for row in read_records(path)]
    connection.execute("DELETE FROM aed_locations")
    connection.executemany(
        """
        INSERT INTO aed_locations
            (aed_id, address, municipality, province, registration_date,
             organisation, source_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)
