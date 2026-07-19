"""Pure tax math for the Anlage-V helper (docs/PRD-tax-module.md).

No DB access here — every function takes plain values and returns floats, so
the whole module is unit-testable without a database (same pattern as
logic.detect_overdue's month helpers).

Money note: computed figures are *estimates to be checked against bank/notary
documents* (the UI says so); float with round(.., 2) is fine here, matching the
rest of the codebase.
"""
from __future__ import annotations

from datetime import date


def _parse(d: str | None) -> date | None:
    if not d or d == "None":
        return None
    return date.fromisoformat(str(d)[:10])


# ── Annuity mortgage (Annuitätendarlehen) ────────────────────────────────────

def annuity_year_breakdown(
    principal: float,
    interest_rate_pct: float,
    tilgung_rate_pct: float,
    start_date: str,
    year: int,
) -> dict:
    """Interest (Schuldzinsen) and principal (Tilgung) paid in `year`.

    Standard German annuity: constant monthly payment
    principal × (Sollzins + anfängliche Tilgung) / 12; each month interest is
    charged on the remaining balance, the rest of the payment amortizes. The
    interest share therefore declines every month — a flat monthly_interest×12
    over-states the deductible amount.

    First payment is assumed in the month of `start_date`. The final payment
    is capped so the balance never goes below zero.
    """
    start = _parse(start_date)
    monthly_rate = interest_rate_pct / 100.0 / 12.0
    payment = principal * (interest_rate_pct + tilgung_rate_pct) / 100.0 / 12.0

    balance = float(principal)
    interest_ytd = 0.0
    tilgung_ytd = 0.0
    # Simulate month by month from the first payment through December of `year`.
    m = start.year * 12 + (start.month - 1)
    end_m = year * 12 + 11
    while m <= end_m and balance > 0.005:
        interest = balance * monthly_rate
        # Tilgung 0 (interest-only) legitimately amortizes nothing; never negative.
        amortize = max(min(payment - interest, balance), 0.0)
        if m // 12 == year:
            interest_ytd += interest
            tilgung_ytd += amortize
        balance -= amortize
        m += 1

    return {
        "interest": round(interest_ytd, 2),
        "tilgung": round(tilgung_ytd, 2),
        "balance_end": round(max(balance, 0.0), 2),
        "monthly_payment": round(payment, 2),
    }


# ── AfA (linear building depreciation, §7 Abs. 4 EStG) ───────────────────────

def afa_for_year(
    purchase_price: float,
    building_share_pct: float,
    afa_rate_pct: float,
    purchase_date: str,
    year: int,
) -> dict:
    """Linear AfA for `year`. Base = building share of the purchase price.

    First calendar year is pro-rata by month (purchase month counts fully);
    depreciation stops once the base is exhausted (e.g. after 50 years at 2%).
    """
    start = _parse(purchase_date)
    base = float(purchase_price) * float(building_share_pct) / 100.0
    annual = base * float(afa_rate_pct) / 100.0
    if annual <= 0 or year < start.year:
        return {"afa": 0.0, "base": round(base, 2), "annual": round(annual, 2)}

    # Months of AfA already consumed before `year` begins.
    monthly = annual / 12.0
    total_months_allowed = round(base / monthly) if monthly > 0 else 0
    months_before = 0 if year == start.year else (year - start.year) * 12 - (start.month - 1)
    months_this_year = 12 - (start.month - 1) if year == start.year else 12
    remaining = max(total_months_allowed - months_before, 0)
    months = min(months_this_year, remaining)
    return {
        "afa": round(monthly * months, 2),
        "base": round(base, 2),
        "annual": round(annual, 2),
        "months": months,
    }


# ── Recurring flat costs ─────────────────────────────────────────────────────

def months_active_in_year(valid_from: str | None, valid_to: str | None, year: int) -> int:
    """Whole months a monthly recurring item is active within `year`.
    A month counts when the item is active on the 1st-of-month .. treat the
    validity window at month granularity: from the month of valid_from through
    the month of valid_to (inclusive)."""
    first = _parse(valid_from) or date(1900, 1, 1)
    last = _parse(valid_to) or date(9999, 12, 1)
    start_m = max(first.year * 12 + (first.month - 1), year * 12)
    end_m = min(last.year * 12 + (last.month - 1), year * 12 + 11)
    return max(end_m - start_m + 1, 0)


# ── One-off expenses with §82b spreading ─────────────────────────────────────

def expense_share_for_year(
    expense_date: str, amount: float, distribute_years: int, year: int
) -> float:
    """Deductible share of a one-off expense in `year`.
    distribute_years=1 → all in the payment year (Abflussprinzip);
    n>1 → amount/n in the payment year and each of the n-1 following years."""
    d = _parse(expense_date)
    n = max(int(distribute_years or 1), 1)
    if d.year <= year <= d.year + n - 1:
        return round(float(amount) / n, 2)
    return 0.0


# ── Gap-year income estimate ─────────────────────────────────────────────────

def contract_months_in_year(start_date: str, end_date: str | None, year: int) -> int:
    """Whole months a contract is active within `year` (month granularity,
    same convention as months_active_in_year)."""
    return months_active_in_year(start_date, end_date, year)
