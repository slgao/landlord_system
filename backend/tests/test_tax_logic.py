"""Tests for tax_logic — annuity interest, AfA, cost expansion, §82b spreading."""
import pytest

from tax_logic import (
    annuity_year_breakdown,
    afa_for_year,
    months_active_in_year,
    expense_share_for_year,
    contract_months_in_year,
)


# ── Annuity ──────────────────────────────────────────────────────────────────

def test_annuity_first_year_full():
    # 200k, 3.5% Sollzins, 2% Tilgung, starting January.
    r = annuity_year_breakdown(200_000, 3.5, 2.0, "2025-01-01", 2025)
    assert r["monthly_payment"] == pytest.approx(916.67, abs=0.01)
    # Interest is slightly below the flat 200k×3.5% = 7000 because the balance
    # declines during the year; well above the balance-after-year-1 floor.
    assert 6_900 < r["interest"] < 7_000
    assert r["interest"] + r["tilgung"] == pytest.approx(916.6667 * 12, abs=0.5)
    assert r["balance_end"] == pytest.approx(200_000 - r["tilgung"], abs=0.01)


def test_annuity_interest_declines_over_years():
    y1 = annuity_year_breakdown(200_000, 3.5, 2.0, "2025-01-01", 2025)
    y5 = annuity_year_breakdown(200_000, 3.5, 2.0, "2025-01-01", 2029)
    assert y5["interest"] < y1["interest"]
    assert y5["tilgung"] > y1["tilgung"]


def test_annuity_mid_year_start():
    # Started in October → only 3 payments that year.
    r = annuity_year_breakdown(120_000, 4.0, 2.0, "2025-10-15", 2025)
    assert r["interest"] + r["tilgung"] == pytest.approx(r["monthly_payment"] * 3, abs=0.5)
    # ~3 months of interest on ~full balance: 120000×4%×(3/12) ≈ 1200.
    assert 1_150 < r["interest"] <= 1_200


def test_annuity_year_before_start_is_zero():
    r = annuity_year_breakdown(120_000, 4.0, 2.0, "2025-10-15", 2024)
    assert r["interest"] == 0.0 and r["tilgung"] == 0.0


def test_annuity_paid_off_loan_stops():
    # Tiny loan, huge Tilgung → pays off in well under a year; later years zero.
    r = annuity_year_breakdown(1_000, 2.0, 100.0, "2025-01-01", 2026)
    assert r["interest"] == 0.0
    assert r["balance_end"] == 0.0


def test_annuity_interest_only_loan_terminates():
    # Tilgung 0: nothing amortizes, interest is flat, loop must still end.
    r = annuity_year_breakdown(100_000, 3.0, 0.0, "2025-01-01", 2026)
    assert r["interest"] == pytest.approx(3_000.0, abs=0.01)
    assert r["balance_end"] == 100_000.0


# ── AfA ──────────────────────────────────────────────────────────────────────

def test_afa_full_year():
    # 500k, 80% building, 2% → 8000/yr.
    r = afa_for_year(500_000, 80, 2.0, "2020-01-15", 2023)
    assert r["afa"] == 8_000.0
    assert r["base"] == 400_000.0


def test_afa_first_year_pro_rata():
    # Purchased July → 6 months (Jul–Dec) in the first year.
    r = afa_for_year(500_000, 80, 2.0, "2025-07-10", 2025)
    assert r["afa"] == 4_000.0
    assert r["months"] == 6


def test_afa_before_purchase_zero():
    r = afa_for_year(500_000, 80, 2.0, "2025-07-10", 2024)
    assert r["afa"] == 0.0


def test_afa_exhausts_after_depreciation_period():
    # 2%/yr → 50 years → 600 months. Purchase 2000-01: 2049 full, 2050 zero.
    assert afa_for_year(100_000, 100, 2.0, "2000-01-01", 2049)["afa"] == 2_000.0
    assert afa_for_year(100_000, 100, 2.0, "2000-01-01", 2050)["afa"] == 0.0


# ── Recurring costs ──────────────────────────────────────────────────────────

def test_months_active_full_year():
    assert months_active_in_year("2021-10-25", None, 2025) == 12


def test_months_active_partial():
    assert months_active_in_year("2025-03-01", "2025-08-15", 2025) == 6  # Mar–Aug
    assert months_active_in_year("2024-01-01", "2025-02-10", 2025) == 2  # Jan–Feb


def test_months_active_outside_year():
    assert months_active_in_year("2026-01-01", None, 2025) == 0
    assert months_active_in_year("2020-01-01", "2024-12-31", 2025) == 0


# ── §82b spreading ───────────────────────────────────────────────────────────

def test_expense_no_spread():
    assert expense_share_for_year("2025-06-01", 6_000, 1, 2025) == 6_000.0
    assert expense_share_for_year("2025-06-01", 6_000, 1, 2026) == 0.0


def test_expense_spread_three_years():
    for y, expected in [(2025, 2_000.0), (2026, 2_000.0), (2027, 2_000.0), (2028, 0.0), (2024, 0.0)]:
        assert expense_share_for_year("2025-06-01", 6_000, 3, y) == expected


def test_expense_spread_remainder_lands_in_final_year():
    # 1000/3: 333.33 + 333.33 + 333.34 — shares must sum to the invoice amount.
    shares = [expense_share_for_year("2025-06-01", 1_000, 3, y) for y in (2025, 2026, 2027)]
    assert shares == [333.33, 333.33, 333.34]
    assert sum(shares) == 1_000.0


# ── Contract months (gap-year estimate) ──────────────────────────────────────

def test_contract_months():
    assert contract_months_in_year("2024-05-01", None, 2025) == 12
    assert contract_months_in_year("2025-09-01", "2026-03-31", 2025) == 4  # Sep–Dec
