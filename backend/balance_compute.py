"""Balance-sheet computations — no UI framework required.

Used by the FastAPI reports router to compute the balance sheet.
Pure DB reads + arithmetic — no UI framework or pandas.

Three queries per owner fetch every contract, recurring cost and payment for
the year; the month-by-month figures are then computed in Python. The earlier
version issued three queries per property per month (a few hundred round
trips to the database for one page), which on a hosted database was most of
the dashboard's load time.
"""
import calendar
from datetime import date
from decimal import Decimal
from db import fetch
from tax_logic import monthly_equivalent

_ZERO = Decimal("0")


def _financing(prop_id, owner, year):
    """Rough financing figures for a property in `year`, summed over its
    mortgages: outstanding debt (Restschuld), interest paid (Schuldzinsen) and
    principal repaid (Tilgung = equity built). Returns zeros when the property
    has no mortgage.

    `interest_paid` / `equity_paid` are the figures **so far** in `year`: for
    the current year the simulation stops at the current month, so they are what
    has actually been paid, not a projected year-end. A past year is complete
    and covers all twelve months. `interest_month` / `equity_month` split out
    the current month alone — the annuity payment is constant but the share of
    it that is interest falls every month, and that split is the thing a
    landlord cannot read off the yearly figure. They are None for a past year,
    where "this month" means nothing.
    """
    from tax_logic import annuity_year_breakdown
    today = date.today()
    is_current = int(year) == today.year
    end_month = today.month if is_current else 12
    rows = fetch("SELECT principal, interest_rate_pct, tilgung_rate_pct, start_date "
                 "FROM mortgages WHERE property_id=? AND owner_id=?", (prop_id, owner))
    debt = interest = equity = 0.0
    interest_acq = equity_acq = 0.0
    interest_m = equity_m = 0.0
    for principal, ir, tr, sd in rows:
        try:
            b = annuity_year_breakdown(float(principal), float(ir), float(tr), sd, int(year), end_month)
            # The month on its own is what the year gained in it. In January
            # there is no earlier month to subtract, so the year so far IS it —
            # asking for month 0 would clamp back to January and cancel out.
            prev = (annuity_year_breakdown(float(principal), float(ir), float(tr), sd,
                                           int(year), end_month - 1)
                    if end_month > 1 else None)
        except Exception:
            continue
        debt += b["balance_end"]
        interest += b["interest"]
        equity += b["tilgung"]
        interest_acq += b["interest_total"]
        equity_acq += b["equity_total"]
        interest_m += b["interest"] - (prev["interest"] if prev else 0.0)
        equity_m += b["tilgung"] - (prev["tilgung"] if prev else 0.0)
    return {"debt_remaining": round(debt, 2),
            "interest_paid": round(interest, 2),
            "equity_paid": round(equity, 2),
            "interest_month": round(interest_m, 2) if is_current else None,
            "equity_month": round(equity_m, 2) if is_current else None,
            "interest_since_acq": round(interest_acq, 2),
            "equity_since_acq": round(equity_acq, 2)}


def _blank(v) -> bool:
    """Date columns are TEXT and a few legacy rows hold the string 'None'."""
    return v is None or str(v) == "None" or str(v) == ""


def expected_rent(contracts, m_start: str, m_end: str) -> Decimal:
    """Expected rent for one property in the month [m_start, m_end].

    `contracts` is an iterable of (apartment_id, rent, start_date, end_date, id).
    For each apartment, take the rent of the most-recently-started contract that
    is active in the month, then sum across apartments. This avoids
    double-counting when two contracts overlap on the *same* apartment (e.g. a
    stale/incorrect end_date on an old contract): one apartment only ever
    contributes one tenant's rent. WG flats model each room as its own
    apartment, so they still sum correctly. Terminated contracts still count for
    the months they were genuinely active.
    """
    best: dict = {}
    for apt, rent, cs, ce, cid in contracts:
        if str(cs) > m_end:
            continue
        if not _blank(ce) and str(ce) < m_start:
            continue
        rank = (str(cs), cid)
        cur = best.get(apt)
        if cur is None or rank > cur[0]:
            best[apt] = (rank, rent)
    return sum((r for _, r in best.values()), _ZERO)


def month_costs(cost_rows, m_start: str, m_end: str, y: int, m: int) -> Decimal:
    """Monthly cost equivalent of a property's recurring costs in one month.

    `cost_rows` is an iterable of (amount, frequency, valid_from, valid_to).
    A cost without a valid_from has always been in force. A quarterly or
    annual bill is spread evenly over its months; a one-time cost lands in the
    month it is dated.
    """
    total = _ZERO
    for amt, freq, vf, vt in cost_rows:
        if not _blank(vf) and str(vf) > m_end:
            continue
        if not _blank(vt) and str(vt) < m_start:
            continue
        if freq == "one-time":
            if not _blank(vf) and str(vf)[:7] == f"{y}-{m:02d}":
                total += amt
        else:
            total += monthly_equivalent(amt, freq)
    return total


def _load_contracts(owner) -> dict:
    out: dict = {}
    for pid, apt, rent, cs, ce, cid in fetch("""
        SELECT a.property_id, c.apartment_id, c.rent, c.start_date, c.end_date, c.id
        FROM contracts c
        JOIN apartments a ON c.apartment_id = a.id
        WHERE c.owner_id = ?
    """, (owner,)):
        out.setdefault(pid, []).append((apt, rent, cs, ce, cid))
    return out


def _load_costs(owner) -> dict:
    out: dict = {}
    for pid, amt, freq, vf, vt in fetch("""
        SELECT a.property_id, fc.amount, fc.frequency, fc.valid_from, fc.valid_to
        FROM flat_costs fc
        JOIN apartments a ON fc.apartment_id = a.id
        WHERE fc.owner_id = ?
    """, (owner,)):
        out.setdefault(pid, []).append((amt, freq, vf, vt))
    return out


def _load_payments(owner, year: int) -> dict:
    """{(property_id, 'YYYY-MM'): Decimal} — everything received in `year`.
    payments.amount is always the EUR value that counts (see the currency
    model), so summing across contracts is sound."""
    rows = fetch("""
        SELECT a.property_id, substr(p.payment_date, 1, 7), COALESCE(SUM(p.amount), 0)
        FROM payments p
        JOIN contracts c ON p.contract_id = c.id
        JOIN apartments a ON c.apartment_id = a.id
        WHERE p.owner_id = ? AND substr(p.payment_date, 1, 4) = ?
        GROUP BY a.property_id, substr(p.payment_date, 1, 7)
    """, (owner, str(year)))
    return {(pid, ym): total for pid, ym, total in rows}


def _compute_snapshot(year: int, owner=None):
    """Return (snapshot, props) suitable for balance_sheet_pdf / the API,
    scoped to the given owner."""
    today = date.today()
    y = int(year)
    max_month = today.month if y == today.year else 12
    properties = fetch("SELECT id, name FROM properties WHERE owner_id=? ORDER BY name", (owner,))

    contracts = _load_contracts(owner)
    costs = _load_costs(owner)
    paid = _load_payments(owner, y)

    snap_start = str(today.replace(day=1))
    snap_end = str(today.replace(day=calendar.monthrange(today.year, today.month)[1]))
    snapshot = []
    for pid, pname in properties:
        exp = expected_rent(contracts.get(pid, []), snap_start, snap_end)
        cst = month_costs(costs.get(pid, []), snap_start, snap_end, today.year, today.month)
        snapshot.append({"name": pname, "expected": float(exp), "costs": float(cst), "net": float(exp - cst)})

    props = []
    for prop_id, prop_name in properties:
        rows = []
        tot_expected = tot_actual = tot_costs = _ZERO
        for m in range(1, max_month + 1):
            m_start = f"{y}-{m:02d}-01"
            m_end = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
            expected = expected_rent(contracts.get(prop_id, []), m_start, m_end)
            actual = paid.get((prop_id, m_start[:7]), _ZERO)
            month_cost = month_costs(costs.get(prop_id, []), m_start, m_end, y, m)
            tot_expected += expected
            tot_actual += actual
            tot_costs += month_cost
            rows.append({
                "Month": date(y, m, 1).strftime("%b %Y"),
                "Expected rent (€)": round(expected, 2),
                "Actual received (€)": round(actual, 2),
                "Variance (€)": round(actual - expected, 2),
                "Costs (€)": round(month_cost, 2),
                "Expected net (€)": round(expected - month_cost, 2),
                "Actual net (€)": round(actual - month_cost, 2),
            })
        props.append({
            "name": prop_name,
            "monthly_rows": rows,
            "tot_expected": tot_expected,
            "tot_actual": tot_actual,
            "tot_costs": tot_costs,
            "flat_rows": [],
            "insights": [],
            **_financing(prop_id, owner, y),
        })
    return snapshot, props
