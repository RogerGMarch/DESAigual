"""Provider-backed geocoding with a durable DuckDB cache."""

import csv
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import httpx
from tqdm import tqdm

from desfibrilator.normalize import (
    address_key,
    locality_matches,
    municipality_key,
    normalized_key,
)


@dataclass(frozen=True)
class GeocodeResult:
    """A normalized geocoder response."""

    latitude: float | None
    longitude: float | None
    confidence: float | None
    matched_address: str | None
    response: Any
    match_precision: str | None = None
    match_status: str = "unresolved"


class CartoCiudadClient:
    """Client for the official CartoCiudad candidate endpoint."""

    provider = "cartociudad"

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: float = 30,
        callback_parameter: str = "callback",
    ) -> None:
        self.endpoint = endpoint
        self.callback_parameter = callback_parameter
        self.client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.client.close()

    def geocode(
        self, address: str, municipality: str | None, province: str | None
    ) -> GeocodeResult:
        """Resolve an address using the best matching CartoCiudad candidate."""
        query = ", ".join(part for part in (address, municipality, province) if part)
        response = self.client.get(
            self.endpoint,
            params={"q": query, self.callback_parameter: "callback"},
        )
        response.raise_for_status()
        payload = _parse_jsonp(response.text)
        return _parse_response(payload, municipality, province)


class NominatimClient:
    """Single-threaded client for a bounded Nominatim fallback pass."""

    provider = "nominatim"

    def __init__(
        self,
        endpoint: str,
        bounds: tuple[float, float, float, float],
        user_agent: str,
        timeout_seconds: float = 30,
        delay_seconds: float = 1.0,
    ) -> None:
        self.endpoint = endpoint
        self.bounds = bounds
        self.delay_seconds = delay_seconds
        self.client = httpx.Client(
            timeout=timeout_seconds,
            headers={"User-Agent": user_agent},
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.client.close()

    def geocode(
        self, address: str, municipality: str | None, province: str | None
    ) -> GeocodeResult:
        """Resolve one address inside the Castilla y Leon bounding box."""
        west, south, east, north = self.bounds
        result = None
        variants = _address_variants(address)
        for index, address_variant in enumerate(variants):
            variant_query = ", ".join(
                part
                for part in (
                    address_variant,
                    municipality,
                    province,
                    "Castilla y Leon",
                    "Espana",
                )
                if part
            )
            response = self.client.get(
                self.endpoint,
                params={
                    "q": variant_query,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "countrycodes": "es",
                    "viewbox": f"{west},{north},{east},{south}",
                    "bounded": 1,
                    "limit": 5,
                    "accept-language": "es",
                },
            )
            response.raise_for_status()
            result = _parse_nominatim(response.json(), municipality, province)
            if result.match_status.startswith("accepted_"):
                return result
            if index + 1 < len(variants):
                time.sleep(self.delay_seconds)
        return result or GeocodeResult(
            None, None, None, None, [], match_status="rejected"
        )


class MapboxClient:
    """Batch client for permanent Mapbox Geocoding v6 requests."""

    provider = "mapbox"

    def __init__(
        self,
        endpoint: str,
        access_token: str,
        bounds: tuple[float, float, float, float],
        timeout_seconds: float = 60,
        permanent: bool = True,
    ) -> None:
        self.endpoint = endpoint
        self.access_token = access_token
        self.bounds = bounds
        self.permanent = permanent
        self.client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.client.close()

    def geocode_batch(
        self,
        rows: list[tuple[str, str | None, str | None]],
    ) -> list[GeocodeResult]:
        """Geocode a batch while constraining searches to Castilla y Leon."""
        west, south, east, north = self.bounds
        queries = [
            {
                "q": ", ".join(
                    part
                    for part in (
                        address,
                        municipality,
                        province,
                        "Castilla y Leon",
                        "Espana",
                    )
                    if part
                ),
                "types": ["address", "street"],
                "country": "ES",
                "bbox": [west, south, east, north],
                "limit": 5,
                "autocomplete": False,
                "language": "es",
            }
            for address, municipality, province in rows
        ]
        response = self.client.post(
            self.endpoint,
            params={"access_token": self.access_token, "permanent": self.permanent},
            json=queries,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("batch", []) if isinstance(payload, dict) else []
        if len(results) != len(rows):
            raise ValueError("Mapbox returned an unexpected batch length")
        return [
            _parse_mapbox_result(result, municipality, province)
            for result, (_, municipality, province) in zip(results, rows, strict=True)
        ]


def geocode_pending(
    connection: duckdb.DuckDBPyConnection,
    client: Any,
    delay_seconds: float = 0.2,
    limit: int | None = None,
) -> int:
    """Geocode uncached AED addresses and persist every provider attempt."""
    cached_keys = {
        row[0]
        for row in connection.sql("SELECT address_key FROM aed_geocodes").fetchall()
    }
    rows = connection.sql(
        """
        SELECT DISTINCT address, municipality, province
        FROM aed_locations
        WHERE address IS NOT NULL AND address <> ''
        """
    ).fetchall()
    rows = [
        row for row in rows if address_key(row[0], row[1], row[2]) not in cached_keys
    ]
    selected_rows = rows[:limit] if limit is not None else rows
    return _geocode_rows(connection, selected_rows, client, delay_seconds)


def geocode_nominatim_pending(
    connection: duckdb.DuckDBPyConnection,
    client: NominatimClient,
    delay_seconds: float = 1.0,
    limit: int | None = None,
    retry_rejected: bool = False,
) -> int:
    """Geocode unresolved addresses not already attempted with Nominatim."""
    rows = _nominatim_pending_rows(connection, retry_rejected)
    selected_rows = rows[:limit] if limit is not None else rows
    return _geocode_rows(connection, selected_rows, client, delay_seconds)


def _nominatim_pending_rows(
    connection: duckdb.DuckDBPyConnection,
    retry_rejected: bool,
) -> list[tuple]:
    """Return unresolved source rows eligible for the fallback pass."""
    accepted_keys = {
        row[0]
        for row in connection.sql(
            """
            SELECT address_key
            FROM aed_geocodes
            WHERE match_status IN ('accepted', 'accepted_exact', 'accepted_street')
            """
        ).fetchall()
    }
    attempt_query = """
        SELECT DISTINCT address_key
        FROM aed_geocode_attempts
        WHERE provider = 'nominatim'
    """
    if retry_rejected:
        attempt_query += " AND match_status LIKE 'accepted%'"
    attempted_keys = {row[0] for row in connection.sql(attempt_query).fetchall()}
    rows = connection.sql(
        """
        SELECT DISTINCT address, municipality, province
        FROM aed_locations
        WHERE address IS NOT NULL AND address <> ''
        """
    ).fetchall()
    rows = [
        row
        for row in rows
        if address_key(row[0], row[1], row[2]) not in accepted_keys
        and address_key(row[0], row[1], row[2]) not in attempted_keys
    ]
    return rows


def _geocode_rows(
    connection: duckdb.DuckDBPyConnection,
    rows: list[tuple],
    client: Any,
    delay_seconds: float,
) -> int:
    count = 0
    seen_keys = set()
    try:
        for address, municipality, province in tqdm(
            rows,
            desc=f"Geocoding with {getattr(client, 'provider', 'test')}",
            unit="address",
        ):
            cache_key = address_key(address, municipality, province)
            if cache_key in seen_keys:
                continue
            seen_keys.add(cache_key)
            try:
                result = client.geocode(address, municipality, province)
            except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
                result = GeocodeResult(
                    latitude=None,
                    longitude=None,
                    confidence=None,
                    matched_address=None,
                    response={
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    },
                    match_status="error",
                )
            _store_result(
                connection,
                cache_key,
                address,
                municipality,
                province,
                getattr(client, "provider", "test"),
                result,
            )
            count += 1
            if delay_seconds:
                time.sleep(delay_seconds)
    finally:
        client.close()
    return count


def _store_result(
    connection: duckdb.DuckDBPyConnection,
    cache_key: str,
    address: str,
    municipality: str | None,
    province: str | None,
    provider: str,
    result: GeocodeResult,
) -> None:
    response_json = json.dumps(result.response, ensure_ascii=False)
    connection.execute(
        """
        INSERT INTO aed_geocode_attempts
            (address_key, provider, latitude, longitude, geocode_confidence,
             matched_address, match_precision, match_status, response_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::JSON)
        """,
        [
            cache_key,
            provider,
            result.latitude,
            result.longitude,
            result.confidence,
            result.matched_address,
            result.match_precision,
            result.match_status,
            response_json,
        ],
    )
    connection.execute(
        """
        INSERT INTO aed_geocodes
            (address_key, address, municipality, province, latitude, longitude,
             geocode_confidence, matched_address, response_json, provider,
             match_precision, match_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?::JSON, ?, ?, ?)
        ON CONFLICT (address_key) DO UPDATE SET
            address = excluded.address,
            municipality = excluded.municipality,
            province = excluded.province,
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            geocode_confidence = excluded.geocode_confidence,
            matched_address = excluded.matched_address,
            response_json = excluded.response_json,
            provider = excluded.provider,
            match_precision = excluded.match_precision,
            match_status = excluded.match_status
        """,
        [
            cache_key,
            address,
            municipality,
            province,
            result.latitude,
            result.longitude,
            result.confidence,
            result.matched_address,
            response_json,
            provider,
            result.match_precision,
            result.match_status,
        ],
    )


def invalidate_cartociudad_cache(
    connection: duckdb.DuckDBPyConnection,
) -> int:
    """Remove stale CartoCiudad first-candidate results for re-selection."""
    source_rows = connection.sql(
        "SELECT address, municipality, province FROM aed_locations"
    ).fetchall()
    expected = {
        address_key(address, municipality, province): (municipality, province)
        for address, municipality, province in source_rows
        if address
    }
    stale = []
    for cache_key, response_json, provider in connection.sql(
        "SELECT address_key, response_json, provider FROM aed_geocodes"
    ).fetchall():
        if provider not in (None, "cartociudad") or cache_key not in expected:
            continue
        response = _decode_json(response_json)
        municipality, province = expected[cache_key]
        if not _is_expected_cartociudad_candidate(response, municipality, province):
            stale.append(cache_key)
    for cache_key in stale:
        connection.execute(
            "DELETE FROM aed_geocodes WHERE address_key = ?", [cache_key]
        )
    return len(stale)


def geocode_all_pending(
    connection: duckdb.DuckDBPyConnection,
    endpoint: str,
    timeout_seconds: float = 30,
    callback_parameter: str = "callback",
    delay_seconds: float = 0.2,
    batch_size: int = 250,
) -> int:
    """Geocode all uncached addresses in bounded, resumable batches."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    total = 0
    batch_number = 0
    while True:
        batch_number += 1
        client = CartoCiudadClient(endpoint, timeout_seconds, callback_parameter)
        processed = geocode_pending(connection, client, delay_seconds, limit=batch_size)
        total += processed
        if processed == 0:
            break
        print(f"Completed CartoCiudad batch {batch_number}: {processed} addresses")
    return total


def geocode_nominatim_all_pending(
    connection: duckdb.DuckDBPyConnection,
    endpoint: str,
    bounds: tuple[float, float, float, float],
    user_agent: str,
    timeout_seconds: float = 30,
    delay_seconds: float = 1.0,
    batch_size: int = 250,
    retry_rejected: bool = False,
) -> int:
    """Run the bounded Nominatim fallback in resumable batches."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    total = 0
    batch_number = 0
    if retry_rejected:
        rows = _nominatim_pending_rows(connection, retry_rejected=True)
        for start in range(0, len(rows), batch_size):
            batch_number += 1
            client = NominatimClient(
                endpoint,
                bounds,
                user_agent,
                timeout_seconds,
                delay_seconds,
            )
            processed = _geocode_rows(
                connection,
                rows[start : start + batch_size],
                client,
                delay_seconds,
            )
            total += processed
            print(f"Completed Nominatim batch {batch_number}: {processed} addresses")
        return total

    while True:
        batch_number += 1
        client = NominatimClient(
            endpoint,
            bounds,
            user_agent,
            timeout_seconds,
            delay_seconds,
        )
        processed = geocode_nominatim_pending(
            connection,
            client,
            delay_seconds,
            limit=batch_size,
            retry_rejected=retry_rejected,
        )
        total += processed
        if processed == 0:
            break
        print(f"Completed Nominatim batch {batch_number}: {processed} addresses")
    return total


def geocode_mapbox_all_pending(
    connection: duckdb.DuckDBPyConnection,
    endpoint: str,
    access_token: str,
    bounds: tuple[float, float, float, float],
    timeout_seconds: float = 60,
    batch_size: int = 100,
    permanent: bool = True,
    retry_rejected: bool = False,
    municipality_centers: dict[str, tuple[float, float]] | None = None,
    proximity_radius_km: float = 35,
) -> int:
    """Geocode unresolved keys with Mapbox in finite batches."""
    if not access_token:
        raise ValueError("MAPBOX_ACCESS_TOKEN is required for Mapbox geocoding")
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("Mapbox batch_size must be between 1 and 1000")

    rows = _mapbox_pending_rows(connection, retry_rejected)
    total = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        client = MapboxClient(
            endpoint,
            access_token,
            bounds,
            timeout_seconds,
            permanent,
            municipality_centers,
            proximity_radius_km,
        )
        try:
            results = client.geocode_batch(batch)
        except (httpx.HTTPError, json.JSONDecodeError, ValueError):
            results = [
                GeocodeResult(
                    None,
                    None,
                    None,
                    None,
                    {"error_type": "MapboxRequestError"},
                    match_status="error",
                )
                for _ in batch
            ]
        finally:
            client.close()
        for row, result in zip(batch, results, strict=True):
            _store_result(
                connection,
                address_key(row[0], row[1], row[2]),
                row[0],
                row[1],
                row[2],
                "mapbox",
                result,
            )
            total += 1
        print(
            f"Completed Mapbox batch {start // batch_size + 1}: {len(batch)} addresses"
        )
    return total


def _mapbox_pending_rows(
    connection: duckdb.DuckDBPyConnection,
    retry_rejected: bool,
) -> list[tuple]:
    """Return only unresolved keys without a previous Mapbox attempt."""
    accepted_keys = {
        row[0]
        for row in connection.sql(
            """
            SELECT address_key
            FROM aed_geocodes
            WHERE match_status IN ('accepted', 'accepted_exact', 'accepted_street')
            """
        ).fetchall()
    }
    attempt_query = """
        SELECT DISTINCT address_key
        FROM aed_geocode_attempts
        WHERE provider = 'mapbox'
    """
    if retry_rejected:
        attempt_query += " AND match_status LIKE 'accepted%'"
    attempted_keys = {row[0] for row in connection.sql(attempt_query).fetchall()}
    rows = connection.sql(
        """
        SELECT DISTINCT address, municipality, province
        FROM aed_locations
        WHERE address IS NOT NULL AND address <> ''
        """
    ).fetchall()
    return [
        row
        for row in rows
        if address_key(row[0], row[1], row[2]) not in accepted_keys
        and address_key(row[0], row[1], row[2]) not in attempted_keys
    ]


def reprocess_mapbox_attempts(
    connection: duckdb.DuckDBPyConnection,
) -> int:
    """Reprocess preserved Mapbox responses after a parser-only correction."""
    source = {
        address_key(address, municipality, province): (
            address,
            municipality,
            province,
        )
        for address, municipality, province in connection.sql(
            "SELECT address, municipality, province FROM aed_locations"
        ).fetchall()
        if address
    }
    municipality_centers = {
        municipality_key(name): (latitude, longitude)
        for name, latitude, longitude in connection.sql(
            "SELECT municipio, latitude, longitude FROM municipalities"
        ).fetchall()
        if name and latitude is not None and longitude is not None
    }
    attempts = connection.sql(
        """
        SELECT address_key, response_json
        FROM aed_geocode_attempts
        WHERE provider = 'mapbox'
        ORDER BY attempted_at
        """
    ).fetchall()
    first_attempts = {}
    for cache_key, response_json in attempts:
        first_attempts.setdefault(cache_key, response_json)

    repaired = 0
    for cache_key, response_json in first_attempts.items():
        if cache_key not in source:
            continue
        payload = _decode_json(response_json)
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if candidates is None:
            continue
        address, municipality, province = source[cache_key]
        result = _parse_mapbox_result(
            {"features": candidates},
            municipality,
            province,
            municipality_centers.get(municipality_key(municipality)),
        )
        _store_result(
            connection,
            cache_key,
            address,
            municipality,
            province,
            "mapbox",
            result,
        )
        repaired += 1
    return repaired


def write_geocode_audit(
    connection: duckdb.DuckDBPyConnection,
    output_path: Path,
) -> int:
    """Write one geocoding outcome row for each AED registry record."""
    source_rows = connection.sql(
        """
        SELECT aed_id, address, municipality, province
        FROM aed_locations
        """
    ).fetchall()
    geocodes = {
        row[0]: row[1:]
        for row in connection.sql(
            """
            SELECT address_key, provider, match_status, match_precision,
                   latitude, longitude, matched_address
            FROM aed_geocodes
            """
        ).fetchall()
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "aed_id",
                "address",
                "municipality",
                "province",
                "provider",
                "match_status",
                "match_precision",
                "latitude",
                "longitude",
                "matched_address",
            ]
        )
        for aed_id, address, municipality, province in source_rows:
            result = geocodes.get(address_key(address, municipality, province), ())
            writer.writerow([aed_id, address, municipality, province, *result])
    return len(source_rows)


def apply_manual_review(
    connection: duckdb.DuckDBPyConnection,
    review_path: Path,
) -> int:
    """Apply only manually reviewed address-level overrides."""
    existing = {
        row[0]: row[1:]
        for row in connection.sql(
            "SELECT address_key, provider, match_status FROM aed_geocodes"
        ).fetchall()
    }
    applied = 0
    with review_path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            review_status = row.get("review_status", "")
            if not review_status.startswith("accepted_manual"):
                continue
            cache_key = address_key(
                row["address"], row["municipality"], row["province"]
            )
            current = existing.get(cache_key)
            if current and current[0] == "manual_review":
                continue
            precision = "exact" if review_status.endswith("exact") else "street"
            result = GeocodeResult(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                confidence=1.0 if precision == "exact" else 0.75,
                matched_address=row.get("matched_address") or None,
                response={
                    "review_reason": row.get("review_reason", ""),
                    "review_status": review_status,
                },
                match_precision=precision,
                match_status=f"accepted_manual_{precision}",
            )
            _store_result(
                connection,
                cache_key,
                row["address"],
                row["municipality"],
                row["province"],
                "manual_review",
                result,
            )
            applied += 1
    return applied


def import_filled_review(
    connection: duckdb.DuckDBPyConnection,
    review_path: Path,
) -> int:
    """Import a reviewed geocode file as the canonical AED coordinate layer."""
    required = {
        "address",
        "municipality",
        "province",
        "latitude",
        "longitude",
        "provider",
        "match_precision",
        "review_status",
        "review_reason",
        "matched_address",
    }
    imported = 0
    with review_path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not required.issubset(reader.fieldnames or set()):
            missing = sorted(required.difference(reader.fieldnames or set()))
            raise ValueError(f"Filled review file is missing columns: {missing}")
        for row in reader:
            cache_key = address_key(
                row["address"], row["municipality"], row["province"]
            )
            has_coordinates = bool(row["latitude"].strip() and row["longitude"].strip())
            precision = row["match_precision"].strip() or None
            status = row["review_status"].strip()
            if has_coordinates and not status.startswith("accepted"):
                raise ValueError(
                    f"Coordinates require an accepted review status for {cache_key}"
                )
            result = GeocodeResult(
                latitude=float(row["latitude"]) if has_coordinates else None,
                longitude=float(row["longitude"]) if has_coordinates else None,
                confidence=1.0 if precision == "exact" else 0.75,
                matched_address=row["matched_address"] or None,
                response={
                    "review_status": status,
                    "review_reason": row["review_reason"],
                },
                match_precision=precision,
                match_status=status or "unresolved",
            )
            _store_result(
                connection,
                cache_key,
                row["address"],
                row["municipality"],
                row["province"],
                row["provider"] or "manual_review",
                result,
            )
            imported += 1
    return imported


def _parse_response(
    payload: Any,
    municipality: str | None = None,
    province: str | None = None,
) -> GeocodeResult:
    if isinstance(payload, dict) and payload.get("features"):
        feature = payload["features"][0]
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        properties = feature.get("properties") or {}
        return GeocodeResult(
            latitude=_number(coordinates[1]) if len(coordinates) > 1 else None,
            longitude=_number(coordinates[0]) if coordinates else None,
            confidence=_number(properties.get("score") or properties.get("accuracy")),
            matched_address=properties.get("label") or properties.get("address"),
            response=feature,
            match_precision="exact" if coordinates else None,
            match_status="accepted_exact" if coordinates else "unresolved",
        )

    candidates = payload if isinstance(payload, list) else payload.get("results", [])
    if municipality is not None or province is not None:
        matching = [
            candidate
            for candidate in candidates
            if _is_expected_cartociudad_candidate(candidate, municipality, province)
        ]
        if not matching:
            return GeocodeResult(
                latitude=None,
                longitude=None,
                confidence=None,
                matched_address=None,
                response={"candidates": candidates},
                match_status="rejected",
            )
        candidate = matching[0]
    else:
        candidate = candidates[0] if candidates else {}
    latitude = _number(candidate.get("lat") or candidate.get("latitude"))
    longitude = _number(
        candidate.get("lon") or candidate.get("lng") or candidate.get("longitude")
    )
    precision = "exact" if candidate.get("type") == "portal" else "street"
    status = "accepted_exact" if precision == "exact" else "accepted_street"
    if latitude is None or longitude is None or (latitude == 0 and longitude == 0):
        precision = None
        status = "unresolved"
    return GeocodeResult(
        latitude=latitude,
        longitude=longitude,
        confidence=_number(candidate.get("score") or candidate.get("accuracy")),
        matched_address=candidate.get("address") or candidate.get("label"),
        response=candidate,
        match_precision=precision,
        match_status=status,
    )


def _parse_mapbox_result(
    payload: Any,
    municipality: str | None,
    province: str | None,
    proximity: tuple[float, float] | None = None,
    proximity_radius_km: float = 35,
) -> GeocodeResult:
    """Parse and validate one Mapbox batch FeatureCollection."""
    features = payload.get("features", []) if isinstance(payload, dict) else []
    matching = [
        feature
        for feature in features
        if _is_expected_mapbox_feature(feature, municipality, province)
    ]
    if not matching and proximity:
        nearby = [
            feature
            for feature in features
            if _is_mapbox_region_province_feature(feature, province)
            and _feature_distance_km(feature, proximity) <= proximity_radius_km
        ]
        if nearby:
            matching = [
                min(
                    nearby,
                    key=lambda feature: _feature_distance_km(feature, proximity),
                )
            ]
    if not matching:
        return GeocodeResult(
            None,
            None,
            None,
            None,
            {"candidates": features},
            match_status="rejected",
        )
    feature = matching[0]
    coordinates = feature.get("geometry", {}).get("coordinates", [])
    properties = feature.get("properties", {})
    match_code = properties.get("match_code", {})
    precision = (
        "exact"
        if properties.get("feature_type") == "address"
        and match_code.get("address_number") in ("matched", "exact")
        else "street"
    )
    return GeocodeResult(
        _number(coordinates[1]) if len(coordinates) > 1 else None,
        _number(coordinates[0]) if coordinates else None,
        None,
        properties.get("full_address")
        or properties.get("name")
        or properties.get("place_formatted"),
        feature,
        match_precision=precision,
        match_status=f"accepted_{precision}",
    )


def _is_expected_mapbox_feature(
    feature: Any,
    municipality: str | None,
    province: str | None,
) -> bool:
    if not isinstance(feature, dict):
        return False
    if not _is_mapbox_region_province_feature(feature, province):
        return False
    if not municipality:
        return True
    properties = feature.get("properties", {})
    context = properties.get("context", {})
    if municipality:
        locality_names = [
            context.get(key, {}).get("name")
            for key in ("place", "locality", "neighborhood")
            if context.get(key, {}).get("name")
        ]
        if locality_names and not any(
            locality_matches(municipality, name) for name in locality_names
        ):
            return False
    return True


def _is_mapbox_region_province_feature(
    feature: Any,
    province: str | None,
) -> bool:
    """Validate Mapbox country, autonomous community, and province context."""
    if not isinstance(feature, dict):
        return False
    properties = feature.get("properties", {})
    context = properties.get("context", {})
    country = context.get("country", {})
    region = context.get("region", {})
    if country.get("country_code", "ES").upper() != "ES":
        return False
    alternate_region = region.get("alternate", {})
    region_codes = {
        region.get("region_code_full"),
        alternate_region.get("region_code_full"),
    }
    if not region_codes.intersection({None, "ES-CL"}):
        return False
    region_names = {region.get("name"), alternate_region.get("name")}
    if not any(
        name and locality_matches("Castilla y Leon", name) for name in region_names
    ):
        return False
    if province:
        province_names = [
            context.get(key, {}).get("name")
            for key in ("district", "region")
            if context.get(key, {}).get("name")
        ]
        if region.get("region_code_full") == "ES-CL":
            province_names = [context.get("district", {}).get("name")]
        if province_names and not any(
            locality_matches(province, name) for name in province_names
        ):
            return False
    return True


def _feature_distance_km(
    feature: dict[str, Any], proximity: tuple[float, float]
) -> float:
    """Calculate approximate great-circle distance to a Mapbox feature."""
    coordinates = feature.get("geometry", {}).get("coordinates", [])
    if len(coordinates) < 2:
        return float("inf")
    longitude, latitude = coordinates[:2]
    center_latitude, center_longitude = proximity
    radius = 6371
    latitude_delta = math.radians(latitude - center_latitude)
    longitude_delta = math.radians(longitude - center_longitude)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(math.radians(center_latitude))
        * math.cos(math.radians(latitude))
        * math.sin(longitude_delta / 2) ** 2
    )
    return radius * 2 * math.asin(min(1, value**0.5))


def _parse_nominatim(
    payload: Any,
    municipality: str | None,
    province: str | None,
) -> GeocodeResult:
    candidates = payload if isinstance(payload, list) else []
    matching = [
        candidate
        for candidate in candidates
        if _is_expected_nominatim_candidate(candidate, municipality, province)
    ]
    if not matching:
        return GeocodeResult(
            latitude=None,
            longitude=None,
            confidence=None,
            matched_address=None,
            response={"candidates": candidates},
            match_status="rejected",
        )
    candidate = next(
        (item for item in matching if item.get("address", {}).get("house_number")),
        matching[0],
    )
    details = candidate.get("address", {})
    precision = "exact" if details.get("house_number") else "street"
    return GeocodeResult(
        latitude=_number(candidate.get("lat")),
        longitude=_number(candidate.get("lon")),
        confidence=_number(candidate.get("importance")),
        matched_address=candidate.get("display_name"),
        response=candidate,
        match_precision=precision,
        match_status=f"accepted_{precision}",
    )


def _is_expected_cartociudad_candidate(
    candidate: Any,
    municipality: str | None,
    province: str | None,
) -> bool:
    if not isinstance(candidate, dict):
        return False
    if candidate.get("comunidadAutonomaCode") not in (None, "07"):
        return False
    if province and candidate.get("province"):
        if normalized_key(candidate["province"]) != normalized_key(province):
            return False
    if municipality and (candidate.get("muni") or candidate.get("poblacion")):
        observed_names = (candidate.get("muni"), candidate.get("poblacion"))
        if not any(locality_matches(municipality, name) for name in observed_names):
            return False
    return True


def _is_expected_nominatim_candidate(
    candidate: Any,
    municipality: str | None,
    province: str | None,
) -> bool:
    if not isinstance(candidate, dict):
        return False
    details = candidate.get("address", {})
    if details.get("country_code") not in (None, "es"):
        return False
    region_code = details.get("ISO3166-2-lvl4")
    if region_code and region_code.upper() != "ES-CL":
        return False
    if details.get("state") and normalized_key(details["state"]) not in (
        "castilla_y_leon",
        "castilla_y_leon",
    ):
        return False
    if province:
        matched_province = details.get("province") or details.get("state_district")
        if matched_province and normalized_key(matched_province) != normalized_key(
            province
        ):
            return False
    if municipality:
        localities = [
            details.get(key)
            for key in (
                "municipality",
                "town",
                "village",
                "hamlet",
                "city",
                "county",
                "suburb",
            )
            if details.get(key)
        ]
        if not any(locality_matches(municipality, locality) for locality in localities):
            return False
    return True


def _address_variants(address: str) -> list[str]:
    """Return conservative address variants for placeholder house numbers."""
    variants = [address]
    without_placeholder = re.sub(r"\s+0$", "", address).strip()
    if without_placeholder and without_placeholder != address:
        variants.append(without_placeholder)
    return variants


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def _parse_jsonp(text: str) -> Any:
    """Parse JSON or the callback-wrapped CartoCiudad response."""
    text = text.strip()
    if text.startswith("callback(") and text.endswith(")"):
        text = text[len("callback(") : -1]
    return json.loads(text)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
