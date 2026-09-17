from desfibrilator.normalize import (
    address_key,
    locality_matches,
    normalize_aed,
    normalize_municipality,
)


def test_normalize_municipality_accepts_accented_headers():
    row = {
        "Municipio": "Ávila",
        "Cod. INE": "05019",
        "Población": "5.432",
        "Longitud": "-4,7",
        "Latitud": "40,65",
    }

    normalized = normalize_municipality(row)

    assert normalized[0] == "Ávila"
    assert normalized[3] == "05019"
    assert normalized[4:] == (5432, -4.7, 40.65, None)


def test_normalize_aed_builds_canonical_shape():
    row = {
        "Número de serie": "AED-1",
        "Tipo de vía": "Calle",
        "Vía": "Mayor",
        "Número": "1",
        "Municipio": "León",
        "Provincia": "León",
        "Empresa": "Ayuntamiento de León",
    }

    assert normalize_aed(row)[:4] == ("AED-1", "Calle Mayor 1", "León", "León")
    assert normalize_aed(row)[5] == "Ayuntamiento de León"


def test_address_key_is_stable_across_accents_and_punctuation():
    assert address_key("Calle Mayor, 1", "León", "León") == address_key(
        "calle mayor 1", "Leon", "Leon"
    )


def test_locality_matches_province_prefix():
    assert locality_matches("LEON", "provincia de León")
