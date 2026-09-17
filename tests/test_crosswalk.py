from desfibrilator.crosswalk import resolve_municipality


def test_cadastre_id_must_not_be_treated_as_ine():
    names = {"37192": ("MILANO", "37")}
    by_name = {("MIRANDA DE AZAN", "37"): ("37192", "Miranda de Azán", 451)}
    assert resolve_municipality("37192", names, by_name) is None


def test_verified_name_match_can_change_code():
    names = {"24900": ("León", "24")}
    by_name = {("LEON", "24"): ("24089", "LEÓN", 123446)}
    assert resolve_municipality("24900", names, by_name)[0] == "24089"


def test_missing_manifest_and_wrong_province_do_not_match():
    by_name = {("LEON", "24"): ("24089", "LEÓN", 123446)}
    assert resolve_municipality("24089", {}, by_name) is None
    assert resolve_municipality("24900", {"24900": ("LEÓN", "05")}, by_name) is None
