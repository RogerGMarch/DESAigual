"""Normalize common Spanish open-data column names and values."""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


def normalized_key(value: str) -> str:
    """Make a source column name comparable across accents and punctuation."""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def value_for(row: Mapping[str, Any], aliases: Iterable[str]) -> Any:
    """Return the first non-empty value matching a list of column aliases."""
    indexed = {normalized_key(key): value for key, value in row.items()}
    for alias in aliases:
        value = indexed.get(normalized_key(alias))
        if value is not None and str(value).strip():
            return value
    return None


def normalize_municipality(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Map one JCyL municipality row to the canonical table shape."""
    return (
        value_for(row, ("municipio", "municipality", "nombre")),
        value_for(row, ("cod_municipio", "codigo_municipio")),
        value_for(row, ("cod_provincia", "codigo_provincia")),
        value_for(row, ("cod_ine", "codigo_ine", "codigo_ine_municipio")),
        _integer(value_for(row, ("poblacion", "population", "habitantes"))),
        _float(value_for(row, ("longitud", "longitude", "lon"))),
        _float(value_for(row, ("latitud", "latitude", "lat"))),
        value_for(row, ("fecha_actualizacion", "updated_at", "ultima_actualizacion")),
    )


def normalize_aed(row: Mapping[str, Any]) -> tuple[Any, ...]:
    """Map one JCyL AED row to the canonical table shape."""
    address = _aed_address(row)
    return (
        value_for(
            row,
            ("aed_id", "id", "numero_de_serie", "numero_serie", "n_serie", "serie"),
        ),
        address,
        value_for(row, ("municipio", "municipality", "localidad")),
        value_for(row, ("provincia", "province")),
        value_for(row, ("fecha_alta", "fecha_registro", "registration_date")),
        value_for(
            row,
            ("organizacion", "organización", "titular", "empresa", "organisation"),
        ),
        value_for(row, ("fecha_actualizacion", "updated_at", "ultima_actualizacion")),
    )


def _aed_address(row: Mapping[str, Any]) -> Any:
    """Build a street address from split DESA registry fields."""
    street_parts = (
        value_for(row, ("tipo_via", "tipo_de_via", "street_type")),
        value_for(row, ("via", "street", "calle")),
        value_for(row, ("numero", "number", "portal")),
    )
    street_address = " ".join(str(part).strip() for part in street_parts if part)
    return street_address or value_for(
        row,
        ("direccion", "address", "domicilio", "ubicacion"),
    )


def address_key(address: str, municipality: str | None, province: str | None) -> str:
    """Build a stable key for the permanent geocoding cache."""
    parts = (address, municipality or "", province or "")
    return "|".join(normalized_key(part) for part in parts)


def municipality_key(value: str | None) -> str:
    """Normalize Spanish municipality names, including trailing articles."""
    key = normalized_key(value or "")
    for article in ("el", "la", "los", "las"):
        suffix = f"_{article}"
        if key.endswith(suffix):
            return f"{article}_{key[: -len(suffix)]}"
    return key


def locality_matches(expected: str | None, observed: str | None) -> bool:
    """Compare municipality or settlement names without overmatching short names."""
    expected_key = _strip_province_prefix(municipality_key(expected))
    observed_key = _strip_province_prefix(municipality_key(observed))
    if not expected_key or not observed_key:
        return False
    if expected_key == observed_key:
        return True
    return len(expected_key) >= 5 and (
        expected_key in observed_key or observed_key in expected_key
    )


def _strip_province_prefix(value: str) -> str:
    """Remove administrative prefixes returned by Spanish geocoders."""
    for prefix in ("provincia_de_", "province_of_"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _integer(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(".", "").replace(",", ".")))
    except ValueError:
        return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None
