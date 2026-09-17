"""Ingest the hospital destinations used by the accessibility analysis."""

import argparse
import hashlib
import re
from pathlib import Path
from typing import Any

import duckdb
from tqdm import tqdm

from desfibrilator.ingest import read_records
from desfibrilator.schema import create_schema


def ingest_hospitals(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    source_updated_at: str | None = None,
) -> int:
    """Replace hospital rows with a normalized CSV or JSON source.

    The source should already contain hospitals with emergency care. If it
    contains an emergency-capability column, values such as ``no`` and
    ``false`` are excluded by the accessibility stage. When that column is
    absent, rows are treated as emergency-capable and the source must be
    documented as pre-filtered.
    """
    source_rows = read_records(path)
    rows = [
        normalize_hospital(row, index, source_updated_at)
        for index, row in tqdm(
            enumerate(source_rows),
            total=len(source_rows),
            desc="Loading hospitals",
            unit="hospital",
        )
    ]
    if not rows:
        raise ValueError(f"Hospital source contains no records: {path}")
    connection.execute("DELETE FROM hospitals")
    connection.executemany(
        """
        INSERT INTO hospitals
            (hospital_id, name, municipality, province, address, longitude,
             latitude, emergency_capable, source_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def normalize_hospital(
    row: dict[str, Any], index: int, source_updated_at: str | None = None
) -> tuple:
    """Normalize one hospital record into the canonical table shape."""
    name = _clean(_value(row, "name", "nombre", "hospital", "centro"))
    municipality = _clean(_value(row, "municipality", "municipio", "localidad"))
    province = _clean(_value(row, "province", "provincia"))
    address = _clean(_value(row, "address", "direccion", "dirección", "domicilio"))
    hospital_id = _clean(
        _value(row, "hospital_id", "id", "codigo", "código", "cod_centro")
    )
    if not hospital_id:
        identity = "|".join(value or "" for value in (name, municipality, address))
        hospital_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    longitude = _number(_value(row, "longitude", "lon", "longitud", "x"))
    latitude = _number(_value(row, "latitude", "lat", "latitud", "y"))
    emergency_value = _value(
        row,
        "emergency_capable",
        "emergency",
        "urgencias",
        "emergencias",
        "acute_care",
    )
    emergency_capable = True if emergency_value is None else _as_bool(emergency_value)
    updated = source_updated_at or _clean(
        _value(row, "source_updated_at", "updated_at", "fecha_actualizacion")
    )
    if longitude is None or latitude is None:
        raise ValueError(
            f"Hospital {hospital_id!r} has no valid longitude/latitude; geocode it "
            "before running the accessibility stage"
        )
    if not name:
        raise ValueError(f"Hospital {hospital_id!r} has no name")
    return (
        hospital_id,
        name,
        municipality,
        province,
        address,
        longitude,
        latitude,
        emergency_capable,
        updated,
    )


def _value(row: dict[str, Any], *aliases: str) -> Any:
    normalized = {_key(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(_key(alias))
        if value not in (None, ""):
            return value
    return None


def _key(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("á", "a").replace("é", "e").replace("í", "i")
    value = value.replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    return float(text)


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() not in {
        "0",
        "false",
        "f",
        "no",
        "n",
        "not",
        "no_aplica",
        "sin urgencias",
    }


def main() -> None:
    """Load a hospital source into the configured DuckDB database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--database", type=Path, default=Path("data/processed/urban_network.duckdb")
    )
    parser.add_argument("--source-updated-at", default=None)
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(args.database)) as connection:
        create_schema(connection)
        count = ingest_hospitals(connection, args.input, args.source_updated_at)
    print(f"Loaded {count} hospitals from {args.input}")


if __name__ == "__main__":
    main()
