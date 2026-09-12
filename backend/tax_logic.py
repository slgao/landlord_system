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

# ── Zinsbindung (the fixed-rate period) ──────────────────────────────────────
# A German mortgage fixes its Sollzins for a term — typically ten years — and
# reprices at the end of it. Projecting today's rate to payoff therefore
# invents a rate: a 2018 loan at 1.44 % is a 2028 loan at whatever the market
# then offers. When a loan records `fixed_until` the simulation switches rate
# from the month after it.
#
# What does NOT change at the reset is the monthly payment. That is the usual
# Prolongation in practice ("gleichbleibende Rate"): the balance is what it is,
# you keep paying what you pay, and the Tilgung share absorbs the new rate —
# so a higher rate shows up as a later payoff and more interest, not a bigger
# bill. (A rate high enough that interest alone exceeds the payment would never
# amortize; `annuity_schedule`'s `max_years` guard still terminates it.)

# Used when a loan has a `fixed_until` but no follow-up rate of its own. It is
# an assumption, not a forecast — the API reports which loans fell back to it
# so the UI can say so.
DEFAULT_FOLLOW_UP_RATE_PCT = 4.0


def follow_up_rate(interest_rate_pct: float, fixed_until: str | None,
                   follow_up_rate_pct: float | None) -> tuple[float | None, bool]:
    """(rate after the reset, whether it was assumed). None when the loan has
    no Zinsbindung on file and the current rate simply runs on."""
    if not _parse(fixed_until):
        return None, False
    if follow_up_rate_pct is None:
        return DEFAULT_FOLLOW_UP_RATE_PCT, True
    return float(follow_up_rate_pct), False


def _rate_picker(interest_rate_pct, fixed_until, follow_up_rate_pct):
    """month-index → monthly interest rate, honouring the reset."""
    after, _ = follow_up_rate(interest_rate_pct, fixed_until, follow_up_rate_pct)
    base = interest_rate_pct / 100.0 / 12.0
    if after is None:
        return lambda m: base
    end = _parse(fixed_until)
    end_m = end.year * 12 + (end.month - 1)
    new = after / 100.0 / 12.0
    return lambda m: base if m <= end_m else new


def annuity_year_breakdown(
    principal: float,
    interest_rate_pct: float,
    tilgung_rate_pct: float,
    start_date: str,
    year: int,
    end_month: int = 12,
    fixed_until: str | None = None,
    follow_up_rate_pct: float | None = None,
) -> dict:
    """Interest (Schuldzinsen) and principal (Tilgung) paid in `year`.

    Standard German annuity: constant monthly payment
    principal × (Sollzins + anfängliche Tilgung) / 12; each month interest is
    charged on the remaining balance, the rest of the payment amortizes. The
    interest share therefore declines every month — a flat monthly_interest×12
    over-states the deductible amount.

    First payment is assumed in the month of `start_date`. The final payment
    is capped so the balance never goes below zero.

    `end_month` (1–12) stops the simulation at that month of `year` — pass the
    current month for a mid-year "as of now" snapshot (balance_end / *_ytd /
    *_total then reflect what's actually been paid so far, not a projected
    year-end). Defaults to 12 (full year), which is what the tax module wants.

    `fixed_until` / `follow_up_rate_pct` reprice the loan at the end of its
    Zinsbindung — see the note above. Omitted, the current rate runs on, which
    is what every caller did before the Zinsbindung was recorded.
    """
    start = _parse(start_date)
    rate_at = _rate_picker(interest_rate_pct, fixed_until, follow_up_rate_pct)
    payment = principal * (interest_rate_pct + tilgung_rate_pct) / 100.0 / 12.0

    balance = float(principal)
    interest_ytd = 0.0
    tilgung_ytd = 0.0
    interest_total = 0.0  # cumulative interest since acquisition through the end month
    # Simulate month by month from the first payment through `end_month` of `year`.
    m = start.year * 12 + (start.month - 1)
    end_m = year * 12 + (max(1, min(12, end_month)) - 1)
    if m > end_m:
        # The loan has not been drawn yet as of this year/month. Nothing has been
        # paid — and, the part that is easy to get wrong, nothing is *owed*: the
        # principal only becomes debt on disbursement. Falling through would leave
        # `balance` at its initial value and report the whole principal as
        # outstanding, which is what made a balance sheet for a year before a
        # purchase show that property's mortgage.
        return {"interest": 0.0, "tilgung": 0.0, "balance_end": 0.0,
                "monthly_payment": round(payment, 2),
                "interest_total": 0.0, "equity_total": 0.0}
    while m <= end_m and balance > 0.005:
        interest = balance * rate_at(m)
        # Tilgung 0 (interest-only) legitimately amortizes nothing; never negative.
        amortize = max(min(payment - interest, balance), 0.0)
        interest_total += interest
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
        # Cumulative since acquisition (loan start) through end of `year`:
        "interest_total": round(interest_total, 2),
        "equity_total": round(float(principal) - max(balance, 0.0), 2),
    }


def annuity_schedule(
    principal: float,
    interest_rate_pct: float,
    tilgung_rate_pct: float,
    start_date: str,
    max_years: int = 60,
    fixed_until: str | None = None,
    follow_up_rate_pct: float | None = None,
) -> list[dict]:
    """Year-by-year life of an annuity loan, from the first payment to payoff.

    Same month-by-month simulation as `annuity_year_breakdown` — the two agree
    year for year (there is a test pinning that) — but walked once instead of
    re-simulated per year, so a 30-year loan costs one pass rather than thirty.

    Each row is a calendar year: `interest` and `tilgung` are what is paid
    *within* that year (they sum to the annuity payments made in it, which is
    less than 12 × payment in the first and last years), `balance_end` is the
    Restschuld once December is booked, and the `*_cum` fields run from the
    loan's start. `paid_off_year` is therefore just the last row's year.

    `max_years` is a termination guard, not a business rule: a loan with 0%
    Tilgung amortizes nothing and would otherwise loop forever.
    """
    start = _parse(start_date)
    payment = float(principal) * (interest_rate_pct + tilgung_rate_pct) / 100.0 / 12.0
    if start is None or payment <= 0 or float(principal) <= 0:
        return []

    rate_at = _rate_picker(interest_rate_pct, fixed_until, follow_up_rate_pct)
    balance = float(principal)
    interest_cum = tilgung_cum = 0.0
    rows: list[dict] = []
    year = start.year
    interest_y = tilgung_y = 0.0
    months_y = 0

    def flush():
        rows.append({
            "year": year,
            "interest": round(interest_y, 2),
            "tilgung": round(tilgung_y, 2),
            "payment": round(interest_y + tilgung_y, 2),
            "balance_end": round(max(balance, 0.0), 2),
            "interest_cum": round(interest_cum, 2),
            "tilgung_cum": round(tilgung_cum, 2),
            "months": months_y,
        })

    m = start.year * 12 + (start.month - 1)
    last_m = (start.year + max_years) * 12 + (start.month - 1)
    while balance > 0.005 and m <= last_m:
        if m // 12 != year:
            flush()
            year = m // 12
            interest_y = tilgung_y = 0.0
            months_y = 0
        interest = balance * rate_at(m)
        # Tilgung 0 (interest-only) legitimately amortizes nothing; never negative.
        # The final payment is capped at the balance so it cannot overshoot.
        amortize = max(min(payment - interest, balance), 0.0)
        balance -= amortize
        interest_y += interest
        tilgung_y += amortize
        interest_cum += interest
        tilgung_cum += amortize
        months_y += 1
        m += 1
    flush()
    return rows


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
    n>1 → amount/n in the payment year and each of the n-1 following years.
    The final year takes the rounding remainder so the shares sum exactly to
    the invoice amount (1000/3 → 333.33, 333.33, 333.34)."""
    d = _parse(expense_date)
    n = max(int(distribute_years or 1), 1)
    if not (d.year <= year <= d.year + n - 1):
        return 0.0
    share = round(float(amount) / n, 2)
    if year == d.year + n - 1:
        return round(float(amount) - share * (n - 1), 2)
    return share


# ── Gap-year income estimate ─────────────────────────────────────────────────

def contract_months_in_year(start_date: str, end_date: str | None, year: int) -> int:
    """Whole months a contract is active within `year` (month granularity,
    same convention as months_active_in_year)."""
    return months_active_in_year(start_date, end_date, year)


# ── Recurring cost frequencies ───────────────────────────────────────────────

# The flat_costs form offers these frequencies. Anything unknown (or NULL on a
# legacy row) is treated as monthly, which is what every consumer assumed
# before the frequency was honoured at all.
FREQUENCY_MONTHS = {"monthly": 1, "quarterly": 3, "annually": 12, "annual": 12, "yearly": 12}


def monthly_equivalent(amount, frequency: str | None):
    """The per-month share of a recurring amount billed at `frequency`.

    A one-time cost has no monthly equivalent — it belongs to the month it
    was paid in — so it returns 0 here; callers place it themselves.
    Works on Decimal as well as float so the balance sheet keeps its
    precision and the tax report keeps its floats.
    """
    if frequency == "one-time":
        return amount * 0
    months = FREQUENCY_MONTHS.get(frequency or "monthly", 1)
    return amount / months if months != 1 else amount


# ── Calling the two above from a stored mortgage row ────────────────────────
# Every caller reads the same six columns; these keep the Zinsbindung from
# being forgotten at one call site and silently projecting the old rate.

def _terms(m: dict) -> tuple:
    return (float(m["principal"]), float(m["interest_rate_pct"]),
            float(m["tilgung_rate_pct"]), m["start_date"],
            m.get("fixed_until"), m.get("follow_up_rate_pct"))


def schedule_for(m: dict, max_years: int = 60) -> list[dict]:
    p, i, t, s, fu, fr = _terms(m)
    return annuity_schedule(p, i, t, s, max_years, fixed_until=fu, follow_up_rate_pct=fr)


def year_breakdown_for(m: dict, year: int, end_month: int = 12) -> dict:
    p, i, t, s, fu, fr = _terms(m)
    return annuity_year_breakdown(p, i, t, s, year, end_month,
                                  fixed_until=fu, follow_up_rate_pct=fr)
