"""Berlin's official land values, looked up from the address on file.

Two open services, both Datenlizenz Deutschland Zero 2.0 (public domain, no
attribution required), both free and unauthenticated:

  adressen_berlin — the address register. Gives the *house* coordinate, which
                    is the part that matters: Einbecker Straße crosses three
                    land-value zones within 200 m, and nos. 39 and 57B sit in
                    different ones (1.600 €/m² against 750 €/m²). A street-level
                    geocode lands in the wrong zone often enough to be useless.
  brw<year>       — the Bodenrichtwert zones for one yearly Stichtag.

There is no real-time valuation of German property to be had. Bodenrichtwerte
are official, free and updated once a year (01.01., published each March), and
that is the honest ceiling for open data. What this module returns is a land
value with the Stichtag it was official on; turning it into a flat's worth is
`valuation.py`'s job, and says it is an estimate.

Nothing here touches the database, and every request goes through an injected
`fetch_json` so the tests run without a network.
"""
import json
import re
import unicodedata
import urllib.parse
import urllib.request

ADDRESS_WFS = "https://gdi.berlin.de/services/wfs/adressen_berlin"
ADDRESS_TYPE = "adressen_berlin:adressen_berlin"
LAND_WFS = "https://gdi.berlin.de/services/wfs/brw{year}"
LAND_TYPE = "brw{year}:brw{year}_vector"

# Both services publish in ETRS89 / UTM zone 33N, so a house coordinate can be
# handed straight to the zone query with no reprojection.
CRS = "urn:ogc:def:crs:EPSG::25833"

LICENCE = "Datenlizenz Deutschland Zero 2.0 (Geoportal Berlin)"
_TIMEOUT = 30
_UA = "dachly-landlord-system/1.0 (+private portfolio tool)"


class LookupError_(Exception):
    """The address could not be placed, or no zone covers it."""


def _http_json(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.load(r)


# ── Matching an address to the official register ──────────────────────────────

def normalize_street(name: str) -> str:
    """Fold the ways one Berlin street name gets written into a single key.

    Berlin writes some names as one word ('Weichselstraße') and others as two
    ('Einbecker Straße'), while this app's addresses abbreviate both to
    'Weichselstr.' and 'Einbeckerstr.'. Nothing short of folding both sides
    matches all of them: lowercase, umlauts and ß expanded, spaces and dots
    dropped, and a trailing 'str' or 'strasse' unified.
    """
    s = unicodedata.normalize("NFC", name or "").lower()
    for a, b in (("ß", "ss"), ("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        s = s.replace(a, b)
    s = re.sub(r"[\s.]+", "", s)
    return re.sub(r"(strasse|str)$", "strasse", s)


def parse_address(address: str):
    """'Einbeckerstr.57B, 10315 Berlin' → ('Einbeckerstr', '57', 'B', '10315').

    Returns None when there is no house number to match on, which is the one
    part the register cannot be queried without.
    """
    if not address:
        return None
    head, *rest = address.split(",")
    plz = None
    for part in rest:
        m = re.search(r"\b(\d{5})\b", part)
        if m:
            plz = m.group(1)
    m = re.match(r"^\s*(.*?)[\s.]*(\d+)\s*([A-Za-z]?)\s*$", head.strip())
    if not m:
        return None
    street = m.group(1).strip(" .")
    if not street:
        return None
    return street, m.group(2), (m.group(3) or None), plz


def _street_stem(street: str) -> str:
    """The distinctive head of the name, for a LIKE that catches either
    spelling. 'Einbeckerstr' → 'Einbecker'."""
    stem = re.split(r"str", street, flags=re.I)[0].strip()
    return (stem or street)[:12]


def _quote(v: str) -> str:
    return str(v).replace("'", "''")


def geocode(address: str, fetch_json=_http_json) -> dict:
    """The official address point for `address`.

    Returns {street, hnr, hnr_zusatz, plz, bezirk, ortsteil, east, north,
             matched, ambiguous}. Raises LookupError_ when nothing matches.
    """
    parsed = parse_address(address)
    if not parsed:
        raise LookupError_(
            "No house number in %r — the address register is looked up by street "
            "and number." % (address or ""))
    street, hnr, suffix, plz = parsed

    cql = "str_name LIKE '%s%%' AND hnr=%s" % (_quote(_street_stem(street)), int(hnr))
    if suffix:
        cql += " AND hnr_zusatz='%s'" % _quote(suffix.upper())
    data = fetch_json(ADDRESS_WFS, {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": ADDRESS_TYPE, "COUNT": 50,
        "OUTPUTFORMAT": "application/json", "CQL_FILTER": cql,
    })
    feats = data.get("features") or []
    if not feats:
        raise LookupError_(
            "Berlin's address register has no %s %s%s. Check the street and number — "
            "and note that Bodenrichtwerte are published per federal state, so this "
            "lookup only covers Berlin addresses."
            % (street, hnr, suffix or ""))

    want = normalize_street(street)
    exact = [f for f in feats if normalize_street(f["properties"].get("str_name")) == want]
    pool = exact or feats

    # Narrow in the order the evidence is strong. Berlin has Müllerstraße 9 in
    # three districts, so the postcode on file settles that one; and a street
    # may hold both "12" and "12 A", which can sit in different land-value
    # zones — so a plain "12" must not match "12 A".
    if plz:
        by_plz = [f for f in pool if f["properties"].get("plz") == plz]
        if by_plz:
            pool = by_plz
    want_suffix = (suffix or "").upper()
    by_suffix = [f for f in pool
                 if (f["properties"].get("hnr_zusatz") or "").upper() == want_suffix]
    if by_suffix:
        pool = by_suffix

    picked = pool[0]
    p, geom = picked["properties"], picked["geometry"]["coordinates"]
    return {
        "street": p.get("str_name"), "hnr": p.get("hnr"),
        "hnr_zusatz": p.get("hnr_zusatz"), "plz": p.get("plz"),
        "bezirk": p.get("bez_name"), "ortsteil": p.get("ort_name"),
        "east": float(geom[0]), "north": float(geom[1]),
        "matched": "%s %s%s, %s" % (p.get("str_name"), p.get("hnr"),
                                    p.get("hnr_zusatz") or "", p.get("plz")),
        # Only what narrowing could not separate. Several districts sharing a
        # street name is not ambiguity when the postcode on file picked one.
        "ambiguous": len(pool) > 1,
    }


# ── The land-value zone under a point ─────────────────────────────────────────

def zone_at(east: float, north: float, year: int, fetch_json=_http_json) -> dict:
    """The Bodenrichtwert zone containing this point for `year`'s Stichtag.

    Asked as a true point-in-polygon (INTERSECTS), not a small bounding box: a
    1 m box straddles a zone boundary often enough to return the neighbouring
    zone instead — it disagreed on three of five addresses tried here.
    """
    data = fetch_json(LAND_WFS.format(year=year), {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": LAND_TYPE.format(year=year), "COUNT": 3,
        "OUTPUTFORMAT": "application/json",
        "CQL_FILTER": "INTERSECTS(geom, POINT(%f %f))" % (east, north),
    })
    feats = data.get("features") or []
    if not feats:
        raise LookupError_(
            "No %d Bodenrichtwert zone covers this address. The map may not yet "
            "be published for that year." % year)
    p = feats[0]["properties"]
    return {
        "stichtag": p.get("stichtag") or "%d-01-01" % year,
        "brw": float(p["brw"]),
        "gfz": float(p["gfz"]) if p.get("gfz") is not None else None,
        "nutzung": p.get("nutzung"),
        "beitragszustand": p.get("beitragszustand"),
        "bezirk": p.get("bezirk"),
        "zone_id": str(p.get("brwid")) if p.get("brwid") is not None else None,
    }


def lookup(address: str, year: int, fetch_json=_http_json) -> dict:
    """Address → land value, in two requests. The caller stores the result."""
    point = geocode(address, fetch_json=fetch_json)
    zone = zone_at(point["east"], point["north"], year, fetch_json=fetch_json)
    return {
        **zone,
        "ortsteil": point["ortsteil"],
        "bezirk": zone.get("bezirk") or point["bezirk"],
        "east": point["east"], "north": point["north"],
        "matched_address": point["matched"],
        "ambiguous": point["ambiguous"],
        "source": "Geoportal Berlin brw%d + adressen_berlin" % year,
        "licence": LICENCE,
    }
