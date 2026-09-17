import duckdb

from desfibrilator.geocode import (
    GeocodeResult,
    _address_variants,
    _parse_jsonp,
    _parse_mapbox_result,
    _parse_nominatim,
    _parse_response,
    geocode_pending,
    write_geocode_audit,
)
from desfibrilator.schema import create_schema


class FakeGeocoder:
    def __init__(self):
        self.calls = []

    def geocode(self, address, municipality, province):
        self.calls.append((address, municipality, province))
        return GeocodeResult(41.65, -4.72, 1.0, address, {"lat": 41.65})

    def close(self):
        pass


class FailingGeocoder(FakeGeocoder):
    def geocode(self, address, municipality, province):
        raise ValueError("invalid address")


def test_geocode_pending_persists_and_reuses_cache():
    connection = duckdb.connect(":memory:")
    create_schema(connection)
    connection.execute(
        "INSERT INTO aed_locations (address, municipality, province) VALUES "
        "(?, ?, ?), (?, ?, ?)",
        [
            "Plaza Mayor 1",
            "Valladolid",
            "Valladolid",
            "Plaza Mayor, 1",
            "Valladolid",
            "Valladolid",
        ],
    )
    client = FakeGeocoder()

    assert geocode_pending(connection, client, delay_seconds=0, limit=1) == 1
    assert geocode_pending(connection, client, delay_seconds=0) == 0
    assert len(client.calls) == 1
    assert connection.sql("SELECT count(*) FROM aed_geocodes").fetchone()[0] == 1


def test_geocode_pending_caches_failed_responses():
    connection = duckdb.connect(":memory:")
    create_schema(connection)
    connection.execute(
        "INSERT INTO aed_locations (address, municipality, province) VALUES (?, ?, ?)",
        ["Invalid address", "Soria", "Soria"],
    )

    assert geocode_pending(connection, FailingGeocoder(), delay_seconds=0) == 1
    assert connection.sql(
        "SELECT latitude, response_json->>'error_type' FROM aed_geocodes"
    ).fetchone() == (None, "ValueError")


def test_parse_cartociudad_jsonp_candidate():
    payload = _parse_jsonp(
        'callback([{"address":"PLAZA MAYOR 1, Valladolid",'
        '"lat":41.6523,"lng":-4.7286}])'
    )

    result = _parse_response(payload)

    assert result.latitude == 41.6523
    assert result.longitude == -4.7286
    assert result.matched_address == "PLAZA MAYOR 1, Valladolid"


def test_cartociudad_selects_matching_candidate_over_first_result():
    payload = [
        {
            "province": "Soria",
            "comunidadAutonomaCode": "07",
            "muni": "Soria",
            "type": "portal",
            "lat": 41.76,
            "lng": -2.47,
        },
        {
            "province": "Valladolid",
            "comunidadAutonomaCode": "07",
            "muni": "Valladolid",
            "type": "portal",
            "lat": 41.64,
            "lng": -4.71,
        },
    ]

    result = _parse_response(payload, "Valladolid", "Valladolid")

    assert result.latitude == 41.64
    assert result.longitude == -4.71


def test_write_geocode_audit_includes_unresolved_records(tmp_path):
    connection = duckdb.connect(":memory:")
    create_schema(connection)
    connection.execute(
        "INSERT INTO aed_locations (aed_id, address, municipality, province) "
        "VALUES ('AED-1', 'Calle Mayor 1', 'Valladolid', 'Valladolid')"
    )

    output = tmp_path / "audit.csv"
    assert write_geocode_audit(connection, output) == 1
    assert "AED-1" in output.read_text()


def test_nominatim_accepts_hamlet_and_state_district_fields():
    payload = [
        {
            "lat": "40.8729",
            "lon": "-4.0200",
            "display_name": "Paseo, Valsaín, Segovia, Castilla y León, España",
            "address": {
                "road": "Paseo",
                "hamlet": "Valsaín",
                "state_district": "Segovia",
                "state": "Castilla y León",
                "ISO3166-2-lvl4": "ES-CL",
                "country_code": "es",
            },
        }
    ]

    result = _parse_nominatim(payload, "VALSAIN", "SEGOVIA")

    assert result.match_status == "accepted_street"
    assert result.match_precision == "street"
    assert result.latitude == 40.8729


def test_nominatim_retries_address_without_placeholder_number():
    assert _address_variants("CALLE MAYOR 0") == ["CALLE MAYOR 0", "CALLE MAYOR"]


def test_parse_mapbox_address_feature():
    payload = {
        "features": [
            {
                "geometry": {"coordinates": [-4.72, 41.65]},
                "properties": {
                    "feature_type": "address",
                    "full_address": "Calle Mayor 1, Valladolid",
                    "match_code": {"address_number": "matched"},
                    "context": {
                        "country": {"country_code": "ES"},
                        "region": {
                            "name": "provincia de Valladolid",
                            "region_code_full": "ES-VA",
                            "alternate": {
                                "name": "Castilla y Leon",
                                "region_code_full": "ES-CL",
                            },
                        },
                        "district": {"name": "Valladolid"},
                        "place": {"name": "Valladolid"},
                    },
                },
            }
        ]
    }

    result = _parse_mapbox_result(payload, "Valladolid", "Valladolid")

    assert result.match_status == "accepted_exact"
    assert result.latitude == 41.65
