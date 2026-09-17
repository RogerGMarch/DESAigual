import duckdb

from desfibrilator.hospital import ingest_hospitals, normalize_hospital
from desfibrilator.schema import create_schema


def test_normalize_hospital_accepts_spanish_aliases():
    normalized = normalize_hospital(
        {
            "Nombre": "Hospital Provincial",
            "Municipio": "Ávila",
            "Longitud": "-4,7",
            "Latitud": "40,65",
            "Urgencias": "Sí",
        },
        0,
    )

    assert normalized[1] == "Hospital Provincial"
    assert normalized[5:7] == (-4.7, 40.65)
    assert normalized[7] is True


def test_ingest_hospitals_replaces_rows(tmp_path):
    source = tmp_path / "hospitals.csv"
    source.write_text(
        "id,name,longitude,latitude,emergency\n"
        "H1,Hospital One,-4.7,40.65,true\n"
        "H2,Hospital Two,-4.8,40.66,false\n",
        encoding="utf-8",
    )
    connection = duckdb.connect(":memory:")
    create_schema(connection)

    assert ingest_hospitals(connection, source) == 2
    assert connection.sql(
        "SELECT hospital_id, emergency_capable FROM hospitals ORDER BY hospital_id"
    ).fetchall() == [("H1", True), ("H2", False)]
