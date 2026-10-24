"""Matching this app's addresses to Berlin's official register, and reading the
land-value zone under the result.

Nothing here touches the network: `lookup` takes its fetcher as an argument, so
the tests hand it canned WFS payloads. The cases are the real ones from the
portfolio — the address spellings that failed, and the zone boundary that a
bounding box got wrong.
"""
import pytest

import land_value
from land_value import LookupError_, normalize_street, parse_address


# ── Street-name folding ──────────────────────────────────────────────────────
# Berlin writes some names as one word and others as two, while this app
# abbreviates both. Five of eight properties here failed to match until both
# sides were folded.

@pytest.mark.parametrize("stored,official", [
    ("Einbeckerstr.", "Einbecker Straße"),
    ("Emserstr", "Emser Straße"),
    ("Kamerunerstr.", "Kameruner Straße"),
    ("Rummelsburgerstr.", "Rummelsburger Straße"),
    ("Weichselstr.", "Weichselstraße"),
    ("Müllerstr.", "Müllerstraße"),
    ("Wintersteinstr.", "Wintersteinstraße"),
])
def test_abbreviated_and_official_spellings_fold_together(stored, official):
    assert normalize_street(stored) == normalize_street(official)


def test_different_streets_do_not_fold_together():
    assert normalize_street("Emserstr.") != normalize_street("Einbeckerstr.")
    assert normalize_street("Müllerstraße") != normalize_street("Möllerstraße")


def test_folding_survives_umlauts_and_case():
    assert normalize_street("MÜLLERSTRASSE") == normalize_street("Müllerstraße")


# ── Address parsing ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("addr,expected", [
    ("Weichselstr.57, 12045 Berlin", ("Weichselstr", "57", None, "12045")),
    ("Einbeckerstr.57B, 10315 Berlin", ("Einbeckerstr", "57", "B", "10315")),
    ("Emser Straße 100, 12051 Berlin", ("Emser Straße", "100", None, "12051")),
    ("Müllerstr.9", ("Müllerstr", "9", None, None)),
])
def test_address_parsing(addr, expected):
    assert parse_address(addr) == expected


@pytest.mark.parametrize("addr", ["", None, "Weichselstraße, Berlin", "12045 Berlin"])
def test_an_address_without_a_house_number_is_not_parsed(addr):
    """The register is queried by street *and* number; without one there is
    nothing to ask."""
    assert parse_address(addr) is None


# ── The lookup, with canned payloads ─────────────────────────────────────────

def _addr_feature(street, hnr, zusatz, plz, east, north, bez="Lichtenberg",
                  ort="Friedrichsfelde"):
    return {"properties": {"str_name": street, "hnr": hnr, "hnr_zusatz": zusatz,
                           "plz": plz, "bez_name": bez, "ort_name": ort},
            "geometry": {"type": "Point", "coordinates": [east, north]}}


def _zone_feature(brw, gfz, brwid, stichtag="2026-01-01", bezirk="Lichtenberg"):
    return {"properties": {"brw": brw, "gfz": gfz, "brwid": brwid, "stichtag": stichtag,
                           "nutzung": "W - Wohngebiet", "bezirk": bezirk,
                           "beitragszustand": "Beitragsfrei nach BauGB"}}


def _fetcher(addr_feats, zone_feats, calls=None):
    def fetch_json(url, params):
        if calls is not None:
            calls.append((url, params))
        if "adressen" in url:
            return {"features": addr_feats}
        return {"features": zone_feats}
    return fetch_json


def test_an_abbreviated_address_resolves_to_the_official_one():
    calls = []
    out = land_value.lookup(
        "Einbeckerstr.57B, 10315 Berlin", 2026,
        fetch_json=_fetcher([_addr_feature("Einbecker Straße", "57", "B", "10315",
                                           398592.7, 5818724.3)],
                            [_zone_feature(750, 1.2, 1144)], calls))
    assert out["brw"] == 750.0
    assert out["gfz"] == 1.2
    assert out["stichtag"] == "2026-01-01"
    assert out["matched_address"] == "Einbecker Straße 57B, 10315"
    assert out["east"] == 398592.7 and out["north"] == 5818724.3


def test_the_zone_is_asked_as_a_point_not_a_box():
    """A 1 m bounding box straddles a zone boundary and returned the wrong zone
    for three of five addresses tried. The query must be a point-in-polygon."""
    calls = []
    land_value.lookup("Weichselstr.57, 12045 Berlin", 2026,
                      fetch_json=_fetcher(
                          [_addr_feature("Weichselstraße", "57", None, "12045",
                                         393694.4, 5816199.4)],
                          [_zone_feature(2800, 2.5, 7001, bezirk="Neukölln")], calls))
    zone_call = [c for c in calls if "brw" in c[0]][0]
    assert "INTERSECTS" in zone_call[1]["CQL_FILTER"]
    assert "393694.4" in zone_call[1]["CQL_FILTER"]
    assert "BBOX" not in zone_call[1]


def test_the_house_number_reaches_the_register_as_a_number():
    """Every address point on the street comes back otherwise, and the right
    house decides the zone."""
    calls = []
    land_value.lookup("Einbeckerstr.39, 10315 Berlin", 2026,
                      fetch_json=_fetcher(
                          [_addr_feature("Einbecker Straße", "39", None, "10315",
                                         398469.3, 5818781.9)],
                          [_zone_feature(1600, 2.0, 1740)], calls))
    cql = [c for c in calls if "adressen" in c[0]][0][1]["CQL_FILTER"]
    assert "hnr=39" in cql
    assert "Einbecker" in cql


def test_the_postcode_on_file_picks_between_same_named_addresses():
    feats = [_addr_feature("Einbecker Straße", "39", None, "13187", 1.0, 2.0),
             _addr_feature("Einbecker Straße", "39", None, "10315", 398469.3, 5818781.9)]
    out = land_value.lookup("Einbeckerstr.39, 10315 Berlin", 2026,
                            fetch_json=_fetcher(feats, [_zone_feature(1600, 2.0, 1740)]))
    assert out["matched_address"].endswith("10315")
    assert out["east"] == 398469.3


def test_a_differently_named_street_is_not_a_candidate():
    """'Einbecker Weg 39' is not 'Einbecker Straße 39', even though the broad
    prefix query returns both."""
    feats = [_addr_feature("Einbecker Weg", "39", None, "13187", 3.0, 4.0),
             _addr_feature("Einbecker Straße", "39", None, "10315", 398469.3, 5818781.9)]
    out = land_value.lookup("Einbeckerstr.39", 2026,
                            fetch_json=_fetcher(feats, [_zone_feature(1600, 2.0, 1740)]))
    assert out["matched_address"].startswith("Einbecker Straße")
    assert out["ambiguous"] is False


def test_the_same_street_in_two_postcodes_is_ambiguous_without_one_on_file():
    """Berlin has repeated street names across districts. With no postcode to
    go on the pick is a guess, and the caller is told."""
    feats = [_addr_feature("Einbecker Straße", "39", None, "13187", 1.0, 2.0),
             _addr_feature("Einbecker Straße", "39", None, "10315", 398469.3, 5818781.9)]
    out = land_value.lookup("Einbeckerstr.39", 2026,
                            fetch_json=_fetcher(feats, [_zone_feature(600, 1.0, 1501)]))
    assert out["ambiguous"] is True


def test_a_single_exact_match_is_not_ambiguous():
    out = land_value.lookup("Weichselstr.57, 12045 Berlin", 2026,
                            fetch_json=_fetcher(
                                [_addr_feature("Weichselstraße", "57", None, "12045",
                                               393694.4, 5816199.4)],
                                [_zone_feature(2800, 2.5, 7001)]))
    assert out["ambiguous"] is False


def test_an_unknown_address_says_so_and_that_this_is_berlin_only():
    """Bodenrichtwerte are published per federal state, so a Hamburg flat
    cannot be looked up here and the message has to say why."""
    with pytest.raises(LookupError_, match="only covers Berlin"):
        land_value.lookup("Nirgendwostr.1, 99999 Berlin", 2026,
                          fetch_json=_fetcher([], []))


def test_an_address_outside_every_zone_says_so():
    with pytest.raises(LookupError_, match="Bodenrichtwert zone"):
        land_value.lookup("Weichselstr.57, 12045 Berlin", 2026,
                          fetch_json=_fetcher(
                              [_addr_feature("Weichselstraße", "57", None, "12045",
                                             393694.4, 5816199.4)], []))


def test_a_quote_in_an_address_cannot_break_the_filter():
    """The street name goes into a CQL string, so a quote is doubled."""
    calls = []
    with pytest.raises(LookupError_):
        land_value.lookup("O'Brienstr.1, 10315 Berlin", 2026,
                          fetch_json=_fetcher([], [], calls))
    cql = calls[0][1]["CQL_FILTER"]
    assert "O''Brien" in cql


def test_the_requested_year_selects_the_service_and_layer():
    calls = []
    land_value.lookup("Weichselstr.57, 12045 Berlin", 2025,
                      fetch_json=_fetcher(
                          [_addr_feature("Weichselstraße", "57", None, "12045", 1.0, 2.0)],
                          [_zone_feature(2200, 2.5, 7001, stichtag="2025-01-01")], calls))
    zone_call = [c for c in calls if "brw" in c[0]][0]
    assert zone_call[0].endswith("brw2025")
    assert zone_call[1]["TYPENAMES"] == "brw2025:brw2025_vector"


# ── Narrowing, from cases the real portfolio threw up ────────────────────────

def test_a_plain_house_number_does_not_match_the_lettered_one():
    """Wintersteinstraße holds both '12' and '12 A' at the same postcode, and
    they can sit in different land-value zones. A stored '12' means '12'."""
    feats = [_addr_feature("Wintersteinstraße", "12", "A", "10587", 1.0, 2.0,
                           bez="Charlottenburg-Wilmersdorf", ort="Charlottenburg"),
             _addr_feature("Wintersteinstraße", "12", None, "10587", 385106.3, 5820086.7,
                           bez="Charlottenburg-Wilmersdorf", ort="Charlottenburg")]
    out = land_value.lookup("Wintersteinstr.12, 10587 Berlin", 2026,
                            fetch_json=_fetcher(feats, [_zone_feature(4000, 2.5, 9001)]))
    assert out["matched_address"] == "Wintersteinstraße 12, 10587"
    assert out["east"] == 385106.3
    assert out["ambiguous"] is False


def test_a_lettered_house_number_matches_its_own_entry():
    feats = [_addr_feature("Einbecker Straße", "57", None, "10315", 1.0, 2.0),
             _addr_feature("Einbecker Straße", "57", "B", "10315", 398592.7, 5818724.3)]
    out = land_value.lookup("Einbeckerstr.57B, 10315 Berlin", 2026,
                            fetch_json=_fetcher(feats, [_zone_feature(750, 1.2, 1144)]))
    assert out["matched_address"] == "Einbecker Straße 57B, 10315"
    assert out["east"] == 398592.7


def test_one_street_name_in_three_districts_is_settled_by_the_postcode():
    """Müllerstraße 9 exists in Spandau, Lichterfelde and Mahlsdorf. With the
    postcode on file that is not ambiguity."""
    feats = [_addr_feature("Müllerstraße", "9", None, "12207", 1.0, 2.0,
                           bez="Steglitz-Zehlendorf", ort="Lichterfelde"),
             _addr_feature("Müllerstraße", "9", None, "12623", 3.0, 4.0,
                           bez="Marzahn-Hellersdorf", ort="Mahlsdorf"),
             _addr_feature("Müllerstraße", "9", None, "13585", 378292.4, 5823132.4,
                           bez="Spandau", ort="Spandau")]
    out = land_value.lookup("Müllerstr.9, 13585 Berlin", 2026,
                            fetch_json=_fetcher(feats, [_zone_feature(1000, 2.0, 5001,
                                                                      bezirk="Spandau")]))
    assert out["ortsteil"] == "Spandau"
    assert out["east"] == 378292.4
    assert out["ambiguous"] is False


def test_the_same_street_and_number_twice_over_stays_ambiguous():
    """Nothing on file separates these two, so the pick is a guess."""
    feats = [_addr_feature("Müllerstraße", "9", None, "13585", 1.0, 2.0),
             _addr_feature("Müllerstraße", "9", None, "13585", 3.0, 4.0)]
    out = land_value.lookup("Müllerstr.9, 13585 Berlin", 2026,
                            fetch_json=_fetcher(feats, [_zone_feature(1000, 2.0, 5001)]))
    assert out["ambiguous"] is True


def test_an_unknown_postcode_does_not_discard_every_candidate():
    """One address here has a mistyped postcode. Falling back to the name match
    is better than refusing to place it at all."""
    feats = [_addr_feature("Einbecker Straße", "39", None, "10315", 398469.3, 5818781.9)]
    out = land_value.lookup("Einbeckerstr.39, 10351 Berlin", 2026,
                            fetch_json=_fetcher(feats, [_zone_feature(1600, 2.0, 1740)]))
    assert out["matched_address"] == "Einbecker Straße 39, 10315"
    assert out["brw"] == 1600.0
