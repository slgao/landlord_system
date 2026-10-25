"""A flat cost that changes price.

The amount of a recurring cost is not fixed for the life of the flat: a
Hausgeld of 355 € becomes 358 €. The cost is still one cost, with two
periods — not a second cost, which the balance sheet and the tax report
would add to the first.
"""
from datetime import date

import pytest
from fastapi import HTTPException

from api.routers import flat_costs as fc


@pytest.fixture
def store(monkeypatch):
    """A tiny in-memory flat_costs table behind the router's queries."""
    rows = {}
    seq = {"n": 0}

    def add(apartment_id=1, cost_type="Hausgeld", amount=355.0,
            frequency="monthly", valid_from=None, valid_to=None, owner=1):
        seq["n"] += 1
        rows[seq["n"]] = dict(id=seq["n"], apartment_id=apartment_id, cost_type=cost_type,
                              amount=amount, frequency=frequency, valid_from=valid_from,
                              valid_to=valid_to, owner_id=owner)
        return seq["n"]

    def overlaps(r, frm, to):
        return ((r["valid_from"] or fc._FOREVER_AGO) <= (to or fc._FOREVER)
                and (r["valid_to"] or fc._FOREVER) >= (frm or fc._FOREVER_AGO))

    def fake_fetch(sql, params=()):
        q = " ".join(sql.split())
        if "FROM apartments WHERE id=?" in q:
            return [(params[0],)]
        if q == "SELECT id FROM flat_costs WHERE id=? AND owner_id=?":
            return [(params[0],)] if params[0] in rows else []
        if q.startswith("SELECT id, amount, valid_from, valid_to FROM flat_costs"):
            apt, ctype, owner, exclude, _, to, frm = params
            return [(r["id"], r["amount"], r["valid_from"], r["valid_to"])
                    for r in rows.values()
                    if r["apartment_id"] == apt and r["cost_type"] == ctype
                    and r["owner_id"] == owner and r["id"] != exclude
                    and overlaps(r, frm, to)]
        if "SELECT apartment_id, cost_type, amount, frequency" in q:
            r = rows.get(params[0])
            return [(r["apartment_id"], r["cost_type"], r["amount"], r["frequency"],
                     r["valid_from"], r["valid_to"])] if r else []
        if "FROM flat_costs fc" in q:                      # the _SELECT row shape
            r = rows[params[0]]
            return [(r["id"], r["apartment_id"], "WE 1", "Haus A", r["cost_type"],
                     r["amount"], r["frequency"], r["valid_from"], r["valid_to"])]
        raise AssertionError(f"unexpected query: {q}")

    def fake_execute_returning(sql, params=()):
        ends, cost_id, _owner, apt, ctype, amount, freq, frm, owner = params
        rows[cost_id]["valid_to"] = ends
        return [(add(apt, ctype, amount, freq, frm, None, owner),)]

    monkeypatch.setattr(fc, "fetch", fake_fetch)
    monkeypatch.setattr(fc, "execute_returning", fake_execute_returning)
    monkeypatch.setattr(fc, "insert", lambda table, values: add(*values))
    monkeypatch.setattr(fc, "execute", lambda sql, params=(): None)
    return type("Store", (), {"rows": rows, "add": staticmethod(add)})


# ── the price change ─────────────────────────────────────────────────────────

def test_the_old_price_ends_the_day_before_the_new_one(store):
    cid = store.add(valid_from="2024-01-01")
    out = fc.new_amount(cid, fc.NewAmountIn(amount=358.0, from_date="2025-07-01"), owner=1)
    assert out.previous.valid_to == "2025-06-30"
    assert out.previous.amount == 355.0
    assert out.current.valid_from == "2025-07-01" and out.current.valid_to is None
    assert out.current.amount == 358.0


def test_the_new_period_inherits_type_flat_and_frequency(store):
    cid = store.add(cost_type="Grundsteuer", frequency="quarterly", valid_from="2024-01-01")
    out = fc.new_amount(cid, fc.NewAmountIn(amount=120.0, from_date="2026-01-01"), owner=1)
    assert out.current.cost_type == "Grundsteuer"
    assert out.current.frequency == "quarterly"
    assert out.current.apartment_id == out.previous.apartment_id


def test_the_frequency_can_change_with_the_price(store):
    cid = store.add(frequency="monthly", valid_from="2024-01-01")
    out = fc.new_amount(cid, fc.NewAmountIn(amount=1200.0, from_date="2026-01-01",
                                            frequency="annually"), owner=1)
    assert out.current.frequency == "annually"


def test_a_change_cannot_start_before_the_price_it_replaces(store):
    cid = store.add(valid_from="2025-01-01")
    with pytest.raises(HTTPException) as exc:
        fc.new_amount(cid, fc.NewAmountIn(amount=358.0, from_date="2024-06-01"), owner=1)
    assert exc.value.status_code == 422


def test_a_change_is_refused_when_a_later_period_already_exists(store):
    cid = store.add(valid_from="2024-01-01", valid_to="2024-12-31")
    store.add(amount=358.0, valid_from="2025-01-01")       # already the current price
    with pytest.raises(HTTPException) as exc:
        fc.new_amount(cid, fc.NewAmountIn(amount=360.0, from_date="2025-06-01"), owner=1)
    assert exc.value.status_code == 409


def test_an_unknown_cost_is_404(store):
    with pytest.raises(HTTPException) as exc:
        fc.new_amount(999, fc.NewAmountIn(amount=1.0, from_date="2025-01-01"), owner=1)
    assert exc.value.status_code == 404


# ── the guard that makes the history trustworthy ─────────────────────────────

def test_a_second_open_row_for_the_same_cost_is_refused(store):
    store.add(valid_from="2024-01-01")
    with pytest.raises(HTTPException) as exc:
        fc.create_flat_cost(fc.FlatCostIn(apartment_id=1, cost_type="Hausgeld",
                                          amount=358.0, valid_from="2025-07-01"), owner=1)
    assert exc.value.status_code == 409
    assert "355.00" in exc.value.detail            # names the row in the way


def test_periods_that_do_not_touch_are_fine(store):
    store.add(valid_from="2024-01-01", valid_to="2025-06-30")
    out = fc.create_flat_cost(fc.FlatCostIn(apartment_id=1, cost_type="Hausgeld",
                                            amount=358.0, valid_from="2025-07-01"), owner=1)
    assert out.amount == 358.0


def test_a_different_cost_or_flat_never_clashes(store):
    store.add(valid_from="2024-01-01")
    assert fc.create_flat_cost(fc.FlatCostIn(apartment_id=1, cost_type="Internet",
                                             amount=40.0), owner=1).cost_type == "Internet"
    assert fc.create_flat_cost(fc.FlatCostIn(apartment_id=2, cost_type="Hausgeld",
                                             amount=355.0), owner=1).apartment_id == 2


def test_editing_a_row_does_not_clash_with_itself(store):
    cid = store.add(valid_from="2024-01-01")
    out = fc.update_flat_cost(cid, fc.FlatCostIn(apartment_id=1, cost_type="Hausgeld",
                                                 amount=356.0, valid_from="2024-01-01"), owner=1)
    assert out.id == cid


# ── a price change recorded before it takes effect ───────────────────────────

def test_an_increase_announced_for_next_year_does_not_change_this_year(store):
    """The normal way a Hausgeld increase arrives: the Verwalter announces it
    in autumn, for January. Recording it must not change what the flat costs
    today, and must change it on the day it starts.

    The Flat Costs page used to make this look like nothing had happened — the
    future row was dimmed and labelled "earlier price" while the amount it
    replaces went on showing as the only price there was — which is what sent
    me looking at the dates the reports actually use.
    """
    from decimal import Decimal
    from flat_economics import recurring_costs

    cid = store.add(amount=310.0, valid_from="2026-01-01")
    out = fc.new_amount(cid, fc.NewAmountIn(amount=348.5, from_date="2027-01-01"), owner=1)

    assert out.previous.valid_to == "2026-12-31"
    assert out.current.valid_from == "2027-01-01" and out.current.valid_to is None

    windows = [(r["amount"], r["frequency"], r["valid_from"], r["valid_to"])
               for r in store.rows.values()]
    # Today: the old price, alone — the two periods never overlap, so the
    # reports cannot add them together.
    assert recurring_costs(windows, "2026-10-25") == Decimal("310.00")
    assert recurring_costs(windows, "2026-12-31") == Decimal("310.00")
    # And from the day it starts, the new one, also alone.
    assert recurring_costs(windows, "2027-01-01") == Decimal("348.50")
    assert recurring_costs(windows, "2030-06-15") == Decimal("348.50")


def test_a_second_increase_can_be_recorded_on_top_of_a_future_one(store):
    # Two announcements before either takes effect: the page keeps the "new
    # amount" action on an upcoming price for exactly this.
    cid = store.add(amount=310.0, valid_from="2026-01-01")
    first = fc.new_amount(cid, fc.NewAmountIn(amount=348.5, from_date="2027-01-01"), owner=1)
    second = fc.new_amount(first.current.id,
                           fc.NewAmountIn(amount=352.0, from_date="2028-01-01"), owner=1)
    assert second.previous.valid_from == "2027-01-01"
    assert second.previous.valid_to == "2027-12-31"
    assert second.current.valid_from == "2028-01-01"

    from decimal import Decimal
    from flat_economics import recurring_costs
    windows = [(r["amount"], r["frequency"], r["valid_from"], r["valid_to"])
               for r in store.rows.values()]
    for day, expected in (("2026-10-25", "310.00"), ("2027-06-01", "348.50"),
                          ("2028-01-01", "352.00")):
        assert recurring_costs(windows, day) == Decimal(expected)
