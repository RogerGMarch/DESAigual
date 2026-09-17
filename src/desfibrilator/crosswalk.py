"""Conservative Cadastre-to-INE matching; the numeric codes are not equivalent."""

import unicodedata


def name_key(value: str) -> str:
    """Normalize accents, case and whitespace without guessing truncated names."""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.upper().split())


def resolve_municipality(cadastral_id: str, names: dict, by_name: dict):
    """Return a name/province match, or None; never infer INE from Cadastre ID."""
    if cadastral_id not in names:
        return None
    name, province = names[cadastral_id]
    return by_name.get((name_key(name), str(province).zfill(2)))
