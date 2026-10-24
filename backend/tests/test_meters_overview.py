"""The Meter Readings page's single request.

It used to make six — apartments, readings and one per meter type — and each
also cost a round trip of its own to re-validate the token. The endpoint now
answers all of it in one query as well, and must still return exactly what
those six return, or the page silently renders something subtly different
from what it did before.
"""
import pytest

from api.routers import meters


@pytest.fixture
def stub(monkeypatch):
    """Route every read the six handlers make to canned rows."""
    def fake_fetch(sql, params=()):
        q = " ".join(sql.split())
        if "FROM apartments a JOIN properties p" in q:
            return [(1, 2, "Haus A", "WE 1", "1.OG", 62.5)]
        if "FROM strom_meters sm" in q:
            return [(10, 1, "WE 1", "S-1", "Zähler", "shared")]
        if "FROM gas_meters gm" in q:
            return [(20, 1, "WE 1", "G-1", None, 1.0, 10.0, "shared")]
        if "FROM wasser_meters wm" in q:
            return []
        if "FROM heizung_meters hm" in q:
            return [(40, 1, "WE 1", "H-1", None, 0.1, "Einheiten", 1.0, "room")]
        if "FROM meter_readings" in q:
            return [(5, "strom", 10, "2026-01-01", 123.0, None)]
        if "FROM meter_reading_protocols mrp" in q:
            return []
        raise AssertionError(f"unexpected query: {q}")
    def fake_bundle(parts):
        # The overview asks for all of it in one round trip; each part still
        # carries the query the individual handler uses, so the same canned
        # rows answer both paths.
        return {name: fake_fetch(sql, ps) for name, sql, ps in parts}

    monkeypatch.setattr(meters, "fetch", fake_fetch)
    monkeypatch.setattr(meters, "fetch_bundle", fake_bundle)
    from api.routers import apartments
    monkeypatch.setattr(apartments, "fetch", fake_fetch)
    return fake_fetch


def test_overview_returns_every_section(stub):
    out = meters.meters_overview(owner=1)
    assert [a.name for a in out.apartments] == ["WE 1"]
    assert [r.id for r in out.readings] == [5]
    assert [m.id for m in out.strom] == [10]
    assert [m.id for m in out.gas] == [20]
    assert out.wasser == []                      # an absent type is empty, not missing
    assert [m.id for m in out.heizung] == [40]


def test_overview_matches_the_six_endpoints_exactly(stub):
    """The whole point: one request, same payload."""
    from api.routers.apartments import list_apartments
    out = meters.meters_overview(owner=1)
    assert out.apartments == list_apartments(owner=1)
    assert out.readings == meters.list_readings(owner=1)
    assert out.strom == meters.list_strom_meters(owner=1)
    assert out.gas == meters.list_gas_meters(owner=1)
    assert out.wasser == meters.list_wasser_meters(owner=1)
    assert out.heizung == meters.list_heizung_meters(owner=1)


def test_the_apartment_carries_its_size(stub):
    # The page shows m² and €/m², so the overview has to carry it through.
    assert meters.meters_overview(owner=1).apartments[0].size_sqm == 62.5


def test_overview_is_not_captured_by_a_parameterised_route():
    """/overview must reach its own handler, not /{something}."""
    from api.main import app
    paths = [r.path for r in app.routes if getattr(r, "path", "").startswith("/api/meters")]
    assert "/api/meters/overview" in paths
    # No meters route is a bare /api/meters/{param} that could swallow it.
    assert not any(p.startswith("/api/meters/{") for p in paths)


# ── A nullable column read as a float ────────────────────────────────────────

def test_a_meter_with_empty_numbers_still_lists():
    """`float(None)` took the whole list down with a 500.

    Every one of these columns is nullable, and the write path has a default
    for each — so a row holding NULL (written before the column existed, or by
    hand in SQL) reads back as what the API would have stored, instead of
    making one odd meter hide the other eleven behind an error page.
    """
    gas = meters._gas((20, 1, "WE 1", "G-1", None, None, None, None))
    assert gas.z_zahl == meters.D_Z_ZAHL
    assert gas.brennwert == meters.D_BRENNWERT
    assert gas.scope == meters.D_SCOPE_SHARED

    heizung = meters._heizung((30, 1, "WE 1", "H-1", None, None, None, None, None))
    assert heizung.unit_price == meters.D_UNIT_PRICE
    assert heizung.unit_label == meters.D_UNIT_LABEL
    assert heizung.conversion_factor == meters.D_CONVERSION_FACTOR
    assert heizung.scope == meters.D_SCOPE_ROOM

    assert meters._strom((10, 1, "WE 1", "S-1", None, None)).scope == meters.D_SCOPE_SHARED
    wasser = meters._wasser((40, 1, "WE 1", "W-1", None, None, None))
    assert wasser.type == meters.D_WASSER_TYPE
    assert wasser.scope == meters.D_SCOPE_SHARED


def test_a_stored_value_is_never_overridden_by_the_default():
    gas = meters._gas((20, 1, "WE 1", "G-1", None, 0.95, 11.2, "room"))
    assert (gas.z_zahl, gas.brennwert, gas.scope) == (0.95, 11.2, "room")
    # 0 is a value, not an absence: a heating unit price of zero is deliberate.
    h = meters._heizung((30, 1, "WE 1", "H-1", None, 0, "kWh", 0.5, "shared"))
    assert h.unit_price == 0.0
