import duckdb

from desfibrilator.map import _is_expected_match, create_aed_map
from desfibrilator.schema import create_schema


def test_create_aed_map_writes_only_geocoded_records(tmp_path, monkeypatch):
    monkeypatch.setattr("desfibrilator.map._add_ign_basemap", lambda axis: None)
    connection = duckdb.connect(":memory:")
    create_schema(connection)
    connection.execute(
        "INSERT INTO aed_locations (aed_id, address, municipality, province) VALUES "
        "('AED-1', 'Calle Mayor 1', 'Valladolid', 'Valladolid'), "
        "('AED-2', 'Calle Sin Coordenadas 2', 'Soria', 'Soria')"
    )
    connection.execute(
        """
        INSERT INTO aed_geocodes
            (address_key, address, municipality, province, latitude, longitude,
             geocode_confidence, matched_address, response_json)
        VALUES ('calle_mayor_1|valladolid|valladolid', 'Calle Mayor 1',
                'Valladolid', 'Valladolid', 41.65, -4.72, 1.0,
                'CALLE MAYOR 1, Valladolid', '{}')
        """
    )

    output = tmp_path / "aed_map.png"
    stats = create_aed_map(connection, output)

    assert stats.total_aeds == 2
    assert stats.mapped_aeds == 1
    assert stats.unmapped_aeds == 1
    assert output.exists()
    assert output.read_bytes().startswith(b"\x89PNG")


def test_map_rejects_a_candidate_from_the_wrong_municipality():
    response = {
        "comunidadAutonomaCode": "07",
        "muni": "Soria",
        "province": "Soria",
    }

    assert not _is_expected_match(response, "Valladolid", "Valladolid")
