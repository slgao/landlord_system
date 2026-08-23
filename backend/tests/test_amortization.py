"""Tests for the amortization endpoint's schedule merging.

The math itself is covered in test_tax_logic; what is easy to get wrong here is
folding several loans that start and finish at different times onto one
timeline — see _merge_schedules.
"""
import pytest

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
