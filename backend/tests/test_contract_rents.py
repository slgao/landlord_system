"""The endpoints behind a rent increase.

A tenancy's price changes — §558 raises it, a Staffel steps it, an Indexmiete
tracks it — and each change is a new period beside the old one rather than an
edit of the only number there was.
"""
import pytest
from fastapi import HTTPException

from api.routers import contracts as cr


@pytest.fixture
def store(monkeypatch):
    """An in-memory contracts + contract_rents behind the router's queries."""
    contracts = {1: {"id": 1, "start_date": "2024-05-01", "end_date": None, "owner_id": 1}}
    rents: dict = {}
    seq = {"n": 0}

    def add_period(contract_id=1, valid_from="2024-05-01", rent=1050.0, nkv=230.0,
                   kind="initial", note=None, owner=1):
        seq["n"] += 1
        rents[seq["n"]] = dict(id=seq["n"], contract_id=contract_id, valid_from=valid_from,
                               rent=rent, nebenkosten_vorauszahlung=nkv, kind=kind,
                               note=note, owner_id=owner)
        return seq["n"]

    def fake_fetch(sql, params=()):
        q = " ".join(sql.split())
        if q.startswith("SELECT id FROM contracts WHERE id=?"):
            return [(params[0],)] if params[0] in contracts else []
        if q.startswith("SELECT start_date, end_date FROM contracts"):
            c = contracts.get(params[0])
            return [(c["start_date"], c["end_date"])] if c else []
        if q.startswith("SELECT id, contract_id, valid_from, rent"):
            cid, owner = params
            return [(r["id"], r["contract_id"], r["valid_from"], r["rent"],
                     r["nebenkosten_vorauszahlung"], r["kind"], r["note"])
                    for r in sorted(rents.values(), key=lambda r: r["valid_from"])
                    if r["contract_id"] == cid and r["owner_id"] == owner]
        if "FROM contract_rents WHERE contract_id=? AND valid_from=?" in q and "id<>?" in q:
            cid, vf, exclude, owner = params
            return [(r["id"],) for r in rents.values()
                    if r["contract_id"] == cid and r["valid_from"] == vf
                    and r["id"] != exclude and r["owner_id"] == owner]
        if "FROM contract_rents WHERE contract_id=? AND valid_from=?" in q:
            cid, vf, owner = params
            return [(r["id"],) for r in rents.values()
                    if r["contract_id"] == cid and r["valid_from"] == vf
                    and r["owner_id"] == owner]
        if q.startswith("SELECT id FROM contract_rents WHERE id=?"):
            rid, cid, owner = params
            r = rents.get(rid)
            return [(rid,)] if r and r["contract_id"] == cid and r["owner_id"] == owner else []
        raise AssertionError(f"unexpected query: {q}")

    def fake_execute(sql, params=()):
        q = " ".join(sql.split())
        if q.startswith("INSERT INTO contract_rents"):
            if len(params) == 7:
                cid, vf, rent, nkv, kind, note, owner = params
            else:
                cid, vf, rent, nkv, owner = params
                kind, note = "initial", None
            add_period(cid, vf, rent, nkv, kind, note, owner)
            return
        if q.startswith("UPDATE contract_rents SET valid_from=?"):
            vf, rent, nkv, kind, note, rid, owner = params
            rents[rid].update(valid_from=vf, rent=rent, nebenkosten_vorauszahlung=nkv,
                              kind=kind, note=note)
            return
        if q.startswith("UPDATE contract_rents SET rent=?"):
            rent, nkv, rid, owner = params
            rents[rid].update(rent=rent, nebenkosten_vorauszahlung=nkv)
            return
        if q.startswith("DELETE FROM contract_rents"):
            rents.pop(params[0], None)
            return
        raise AssertionError(f"unexpected statement: {q}")

    monkeypatch.setattr(cr, "fetch", fake_fetch)
    monkeypatch.setattr(cr, "execute", fake_execute)
    add_period()
    return type("Store", (), {"rents": rents, "contracts": contracts,
                              "add": staticmethod(add_period)})


def _in(valid_from, rent, nkv=None, kind="agreed", note=None):
    return cr.RentPeriodIn(valid_from=valid_from, rent=rent,
                           nebenkosten_vorauszahlung=nkv, kind=kind, note=note)


# ── recording an increase ────────────────────────────────────────────────────

def test_an_increase_is_a_new_period_beside_the_old_one(store):
    out = cr.add_rent_period(1, _in("2026-07-01", 1150.0, 260.0), owner=1)
    assert [p.valid_from for p in out] == ["2024-05-01", "2026-07-01"]
    assert [p.rent for p in out] == [1050.0, 1150.0]
    # The old price is untouched — that is the whole point.
    assert out[0].nebenkosten_vorauszahlung == 230.0


def test_the_kind_says_which_paragraph_it_rests_on(store):
    out = cr.add_rent_period(1, _in("2026-07-01", 1150.0, kind="staffel"), owner=1)
    assert out[-1].kind == "staffel"
    assert "§557a" in out[-1].kind_label


def test_a_staffel_can_be_entered_years_ahead(store):
    for year, rent in ((2026, 1100), (2027, 1150), (2028, 1200)):
        cr.add_rent_period(1, _in(f"{year}-01-01", rent, kind="staffel"), owner=1)
    out = cr.list_rent_periods(1, owner=1)
    assert [p.rent for p in out] == [1050.0, 1100.0, 1150.0, 1200.0]
    # Exactly one period is the price being charged today.
    assert sum(1 for p in out if p.current) == 1


def test_the_cold_rent_is_derived_per_period(store):
    out = cr.add_rent_period(1, _in("2026-07-01", 1150.0, 260.0), owner=1)
    assert out[0].cold_rent == 820.0        # 1050 − 230
    assert out[1].cold_rent == 890.0        # 1150 − 260


def test_a_note_records_why(store):
    out = cr.add_rent_period(1, _in("2026-07-01", 1150.0,
                                    note="Mietspiegel 2026"), owner=1)
    assert out[-1].note == "Mietspiegel 2026"


# ── what is refused ──────────────────────────────────────────────────────────

def test_a_price_cannot_start_before_the_tenancy(store):
    with pytest.raises(HTTPException) as e:
        cr.add_rent_period(1, _in("2024-01-01", 1150.0), owner=1)
    assert e.value.status_code == 422
    assert "2024-05-01" in e.value.detail


def test_a_price_cannot_start_after_the_tenancy_ended(store):
    store.contracts[1]["end_date"] = "2026-12-31"
    with pytest.raises(HTTPException) as e:
        cr.add_rent_period(1, _in("2027-01-01", 1150.0), owner=1)
    assert e.value.status_code == 422


def test_two_prices_cannot_start_on_the_same_day(store):
    cr.add_rent_period(1, _in("2026-07-01", 1150.0), owner=1)
    with pytest.raises(HTTPException) as e:
        cr.add_rent_period(1, _in("2026-07-01", 1200.0), owner=1)
    assert e.value.status_code == 409


def test_the_nebenkosten_share_cannot_exceed_the_rent():
    with pytest.raises(ValueError):
        cr.RentPeriodIn(valid_from="2026-07-01", rent=500.0,
                        nebenkosten_vorauszahlung=600.0)


def test_another_landlords_contract_is_not_found(store):
    with pytest.raises(HTTPException) as e:
        cr.add_rent_period(99, _in("2026-07-01", 1150.0), owner=1)
    assert e.value.status_code == 404


# ── correcting and removing ──────────────────────────────────────────────────

def test_a_mistyped_price_can_be_corrected(store):
    out = cr.add_rent_period(1, _in("2026-07-01", 1510.0), owner=1)
    wrong = out[-1].id
    fixed = cr.update_rent_period(1, wrong, _in("2026-07-01", 1150.0, 260.0), owner=1)
    assert fixed[-1].rent == 1150.0


def test_a_correction_cannot_collide_with_another_period(store):
    cr.add_rent_period(1, _in("2026-07-01", 1150.0), owner=1)
    out = cr.add_rent_period(1, _in("2027-01-01", 1200.0), owner=1)
    with pytest.raises(HTTPException) as e:
        cr.update_rent_period(1, out[-1].id, _in("2026-07-01", 1200.0), owner=1)
    assert e.value.status_code == 409


def test_a_period_entered_by_mistake_can_go(store):
    out = cr.add_rent_period(1, _in("2026-07-01", 1150.0), owner=1)
    left = cr.delete_rent_period(1, out[-1].id, owner=1)
    assert [p.valid_from for p in left] == ["2024-05-01"]


def test_the_last_price_cannot_be_removed(store):
    only = cr.list_rent_periods(1, owner=1)[0]
    with pytest.raises(HTTPException) as e:
        cr.delete_rent_period(1, only.id, owner=1)
    assert e.value.status_code == 409
    # A tenancy with no price would be expected to earn nothing, in every
    # month it ever ran.
    assert len(cr.list_rent_periods(1, owner=1)) == 1


# ── which period is "now" ────────────────────────────────────────────────────

def test_the_current_period_is_the_last_one_that_has_started(store):
    cr.add_rent_period(1, _in("2026-07-01", 1150.0), owner=1)
    cr.add_rent_period(1, _in("2099-01-01", 2000.0), owner=1)
    out = cr.list_rent_periods(1, owner=1)
    current = [p for p in out if p.current]
    assert len(current) == 1 and current[0].valid_from == "2026-07-01"


def test_a_tenancy_that_has_not_begun_shows_the_price_it_starts_at(store):
    store.rents.clear()
    store.add(valid_from="2099-01-01", rent=1300.0)
    out = cr.list_rent_periods(1, owner=1)
    assert out[0].current is True
    assert out[0].rent == 1300.0


# ── what an increase carries over ────────────────────────────────────────────

def test_an_increase_keeps_the_nebenkosten_share_already_agreed(store):
    # Saying nothing about the NK share must not turn the rent warm: that
    # would move the Kaltmiete, every €/m² derived from it, and the Umlagen
    # line of the Anlage V.
    out = cr.add_rent_period(1, _in("2026-07-01", 1150.0), owner=1)
    assert out[-1].nebenkosten_vorauszahlung == 230.0
    assert out[-1].cold_rent == 920.0


def test_a_share_given_explicitly_wins(store):
    out = cr.add_rent_period(1, _in("2026-07-01", 1150.0, 260.0), owner=1)
    assert out[-1].nebenkosten_vorauszahlung == 260.0


def test_zero_says_there_is_no_share(store):
    out = cr.add_rent_period(1, _in("2026-07-01", 1150.0, 0.0), owner=1)
    assert out[-1].nebenkosten_vorauszahlung == 0.0
    assert out[-1].cold_rent == 1150.0


def test_a_carried_share_larger_than_the_new_rent_is_refused(store):
    store.rents.clear()
    store.add(valid_from="2024-05-01", rent=1050.0, nkv=900.0)
    with pytest.raises(HTTPException) as e:
        cr.add_rent_period(1, _in("2026-07-01", 500.0), owner=1)
    assert e.value.status_code == 422


# ── §551: what a deposit may be ──────────────────────────────────────────────

def test_a_deposit_within_three_cold_rents_passes_unremarked():
    note = cr._kaution_cap_note(2460.0, 1050.0, 230.0)      # 3 × 820
    assert note["kaution_cap"] == 2460.0
    assert note["kaution_over_cap"] is None


def test_a_deposit_above_the_cap_says_by_how_much():
    note = cr._kaution_cap_note(3000.0, 1050.0, 230.0)
    assert note["kaution_cap"] == 2460.0
    assert note["kaution_over_cap"] == 540.0


def test_the_cap_uses_the_cold_rent_not_the_warm_one():
    # Measuring against the warm rent would allow 3.150 € — a fifth too much,
    # and the tenant can reclaim the difference at any time.
    assert cr._kaution_cap_note(3000.0, 1050.0, 230.0)["kaution_cap"] == 2460.0
    assert cr._kaution_cap_note(3000.0, 1050.0, None)["kaution_cap"] == 3150.0


def test_the_cap_is_measured_against_the_rent_at_signing():
    # §551 measures the deposit against the rent when the tenancy began: a
    # later increase does not retroactively permit a larger deposit. The
    # overview therefore reads the tenancy's first period, not its current one.
    from inspect import getsource
    src = getsource(cr.kaution_overview)
    assert "ORDER BY r.valid_from ASC LIMIT 1" in src


def test_nothing_is_claimed_without_a_rent_on_file():
    note = cr._kaution_cap_note(2000.0, None, None)
    assert note == {"kaution_cap": None, "kaution_over_cap": None}
