"""Tests for the amortization endpoint: schedule merging, and the aggregation
it hands the Financing page.

The math itself is covered in test_tax_logic; what is easy to get wrong here is
folding several loans that start and finish at different times onto one
timeline (see _merge_schedules), and the rules around equity and the
Zinsbindung reset.
"""
from datetime import date

import pytest

from api.routers import tax as tax_router
from api.routers.tax import _merge_schedules
from tax_logic import annuity_schedule


def test_merge_of_one_is_that_schedule():
    s = annuity_schedule(100_000, 3.0, 2.0, "2020-01-01")
    merged = _merge_schedules([s])
    assert [r["year"] for r in merged] == [r["year"] for r in s]
    assert merged[0]["interest"] == pytest.approx(s[0]["interest"], abs=0.01)
    assert merged[-1]["balance_end"] == 0.0


def test_merge_spans_earliest_start_to_latest_payoff():
    a = annuity_schedule(100_000, 3.0, 2.0, "2020-01-01")     # pays off first
    b = annuity_schedule(50_000, 2.0, 1.5, "2024-01-01")       # much slower
    merged = _merge_schedules([a, b])
    assert merged[0]["year"] == 2020
    assert merged[-1]["year"] == max(a[-1]["year"], b[-1]["year"])
    assert merged[-1]["balance_end"] == 0.0


def test_loan_contributes_nothing_before_it_is_drawn():
    a = annuity_schedule(100_000, 3.0, 2.0, "2020-01-01")
    b = annuity_schedule(50_000, 2.0, 2.0, "2025-01-01")
    merged = {r["year"]: r for r in _merge_schedules([a, b])}
    a_by_year = {r["year"]: r for r in a}
    for y in (2020, 2024):
        assert merged[y]["interest"] == pytest.approx(a_by_year[y]["interest"], abs=0.01)
        assert merged[y]["balance_end"] == pytest.approx(a_by_year[y]["balance_end"], abs=0.01)
    # The year the second loan is drawn, the outstanding debt jumps.
    assert merged[2025]["balance_end"] > merged[2024]["balance_end"]


def test_paid_off_loan_keeps_its_totals_in_the_running_sum():
    """The regression this guards: dropping a finished loan from later years
    would make cumulative interest fall — a number that can only ever rise."""
    a = annuity_schedule(100_000, 3.0, 2.0, "2020-01-01")
    b = annuity_schedule(50_000, 2.0, 1.5, "2024-01-01")
    merged = _merge_schedules([a, b])
    cums = [r["interest_cum"] for r in merged]
    assert cums == sorted(cums)
    equity = [r["tilgung_cum"] for r in merged]
    assert equity == sorted(equity)
    # Every euro borrowed is eventually repaid.
    assert merged[-1]["tilgung_cum"] == pytest.approx(150_000, abs=1.0)


def test_merge_of_nothing_is_empty():
    assert _merge_schedules([]) == []


def test_as_of_ignores_a_loan_not_yet_drawn():
    """A loan signed for next year is not debt today, and you are not paying its
    rate yet — the Financing page's Restschuld and Rate both key off this."""
    from api.routers.tax import _as_of
    m = {"principal": 100_000, "interest_rate_pct": 3.0, "tilgung_rate_pct": 2.0,
         "start_date": "2030-01-01"}
    r = _as_of(m, 2026, 8)
    assert r["balance_now"] == 0.0
    assert r["interest_since_start"] == 0.0 and r["tilgung_since_start"] == 0.0
    # The contractual rate is still reported; it is the caller that filters on
    # balance_now before summing it into a property's monthly payment.
    assert r["monthly_payment"] > 0


def test_as_of_on_a_settled_loan():
    from api.routers.tax import _as_of
    m = {"principal": 50_000, "interest_rate_pct": 5.0, "tilgung_rate_pct": 5.0,
         "start_date": "1980-01-01"}
    r = _as_of(m, 2026, 8)
    assert r["balance_now"] == 0.0
    assert r["tilgung_since_start"] == pytest.approx(50_000, abs=1.0)


# ── Aggregation: equity and the Zinsbindung reset ───────────────────────────

# mortgages row order is tax_router._MORTGAGE_COLS
def _loan(mid, pid, label, principal, ir, tr, start, fixed_until=None, follow=None):
    return (mid, pid, label, principal, ir, tr, start, None, fixed_until, follow)


def _install(monkeypatch, properties, loans, apartments=()):
    def fake_fetch(sql, params=()):
        q = " ".join(sql.split())
        if "FROM mortgages" in q:
            return list(loans)
        if "FROM properties" in q:
            return list(properties)
        if "FROM apartments" in q:
            return list(apartments)
        raise AssertionError(f"unexpected query: {q}")
    monkeypatch.setattr(tax_router, "fetch", fake_fetch)


def test_equity_is_value_less_debt(monkeypatch):
    _install(monkeypatch,
             properties=[(1, "Haus A", 300000, "2026-06-30")],
             loans=[_loan(1, 1, "A", 200000, 2.0, 2.0, "2020-01-31")])
    out = tax_router.amortization(owner=1)
    p = out["properties"][0]
    assert p["market_value"] == 300000
    assert p["market_value_date"] == "2026-06-30"
    assert p["equity"] == round(300000 - p["balance_now"], 2)
    assert out["totals"]["equity"] == p["equity"]
    assert out["totals"]["properties_valued"] == out["totals"]["properties_total"] == 1


def test_unvalued_property_reports_no_equity(monkeypatch):
    _install(monkeypatch,
             properties=[(1, "Haus A", None, None)],
             loans=[_loan(1, 1, "A", 200000, 2.0, 2.0, "2020-01-31")])
    out = tax_router.amortization(owner=1)
    assert out["properties"][0]["equity"] is None
    assert out["totals"]["equity"] is None and out["totals"]["market_value"] is None


def test_partly_valued_portfolio_withholds_both_totals(monkeypatch):
    # Pitting one property's value against the whole portfolio's debt would
    # report an equity far below the truth while looking authoritative.
    _install(monkeypatch,
             properties=[(1, "Haus A", 300000, None), (2, "Haus B", None, None)],
             loans=[_loan(1, 1, "A", 200000, 2.0, 2.0, "2020-01-31"),
                    _loan(2, 2, "B", 100000, 2.0, 2.0, "2020-01-31")])
    t = tax_router.amortization(owner=1)["totals"]
    assert t["equity"] is None
    assert t["market_value"] is None
    assert (t["properties_valued"], t["properties_total"]) == (1, 2)


def test_reset_fields_follow_the_zinsbindung(monkeypatch):
    _install(monkeypatch,
             properties=[(1, "Haus A", None, None)],
             loans=[_loan(1, 1, "fixed", 200000, 1.44, 3.0, "2018-06-30", "2028-06-30", 4.5),
                    _loan(2, 1, "open", 50000, 2.0, 2.0, "2020-01-31")])
    p = tax_router.amortization(owner=1)["properties"][0]
    by = {m["label"]: m for m in p["mortgages"]}
    assert by["fixed"]["balance_at_reset"] > 0          # what must be refinanced
    assert by["open"]["balance_at_reset"] is None       # nothing to refinance
    assert by["fixed"]["follow_up_rate_pct"] == 4.5 and by["fixed"]["follow_up_assumed"] is False
    assert by["open"]["follow_up_rate_pct"] is None
    # The property's next reset is the earliest across its loans.
    assert p["next_reset"] == "2028-06-30"


def test_a_missing_follow_up_rate_is_flagged_not_silently_chosen(monkeypatch):
    _install(monkeypatch,
             properties=[(1, "Haus A", None, None)],
             loans=[_loan(1, 1, "fixed", 200000, 1.44, 3.0, "2018-06-30", "2028-06-30", None)])
    m = tax_router.amortization(owner=1)["properties"][0]["mortgages"][0]
    assert m["follow_up_assumed"] is True
    assert m["follow_up_rate_pct"] == tax_router.tax_logic.DEFAULT_FOLLOW_UP_RATE_PCT


def test_repricing_defers_payoff_in_the_endpoint_too(monkeypatch):
    terms = dict(properties=[(1, "Haus A", None, None)])
    _install(monkeypatch, loans=[_loan(1, 1, "x", 200000, 1.44, 3.0, "2018-06-30")], **terms)
    flat = tax_router.amortization(owner=1)["properties"][0]
    _install(monkeypatch, loans=[_loan(1, 1, "x", 200000, 1.44, 3.0, "2018-06-30", "2028-06-30", 4.5)], **terms)
    repriced = tax_router.amortization(owner=1)["properties"][0]
    assert repriced["paid_off_year"] > flat["paid_off_year"]
    assert repriced["interest_lifetime"] > flat["interest_lifetime"]
