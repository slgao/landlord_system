"""Balance-sheet computations — no UI framework required.

Used by the FastAPI reports router to compute the balance sheet.
Pure DB reads + arithmetic — no UI framework or pandas.
"""
import calendar
from datetime import date
from decimal import Decimal
from db import fetch

_ZERO = Decimal("0")


def _financing(prop_id, owner, year):
    """Rough financing figures for a property in `year`, summed over its
    mortgages: outstanding debt at year-end (Restschuld), interest paid
    (Schuldzinsen) and principal repaid (Tilgung = equity built). Returns zeros
    when the property has no mortgage."""
    from tax_logic import annuity_year_breakdown
    rows = fetch("SELECT principal, interest_rate_pct, tilgung_rate_pct, start_date "
                 "FROM mortgages WHERE property_id=? AND owner_id=?", (prop_id, owner))
    debt = interest = equity = 0.0
    for principal, ir, tr, sd in rows:
        try:
            b = annuity_year_breakdown(float(principal), float(ir), float(tr), sd, int(year))
        except Exception:
            continue
        debt += b["balance_end"]
        interest += b["interest"]
        equity += b["tilgung"]
    return {"debt_remaining": round(debt, 2),
            "interest_paid": round(interest, 2),
            "equity_paid": round(equity, 2)}


def _expected_rent(prop_id, m_start, m_end):
    """Expected rent for a property in a month.

    For each apartment, take the rent of the most-recently-started contract that
    is active in the month, then sum across apartments. This avoids
    double-counting when two contracts overlap on the *same* apartment (e.g. a
    stale/incorrect end_date on an old contract): one apartment only ever
    contributes one tenant's rent. WG flats model each room as its own
    apartment, so they still sum correctly. Terminated contracts still count for
    the months they were genuinely active."""
    rows = fetch("""
        SELECT COALESCE(SUM(rent), 0) FROM (
            SELECT DISTINCT ON (c.apartment_id) c.rent
            FROM contracts c
            JOIN apartments a ON c.apartment_id = a.id
            WHERE a.property_id = ?
              AND c.start_date <= ?
              AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= ?)
            ORDER BY c.apartment_id, c.start_date DESC, c.id DESC
        ) t
    """, (prop_id, m_end, m_start))
    return rows[0][0]


def _actual_income(prop_id, m_start, m_end):
    """Sum of payments actually received in a month (all EUR — see the currency
    model: payments.amount is always the EUR value that counts)."""
    return fetch("""
        SELECT COALESCE(SUM(p.amount), 0)
        FROM payments p
        JOIN contracts c ON p.contract_id = c.id
        JOIN apartments a ON c.apartment_id = a.id
        WHERE a.property_id = ? AND p.payment_date BETWEEN ? AND ?
    """, (prop_id, m_start, m_end))[0][0]


def _flat_costs_month(prop_id, m_start, m_end, y, m):
    """Monthly cost equivalent for a property in a given month."""
    rows = fetch("""
        SELECT fc.amount, fc.frequency, fc.valid_from
        FROM flat_costs fc
        JOIN apartments a ON fc.apartment_id = a.id
        WHERE a.property_id = ?
          AND fc.valid_from <= ?
          AND (fc.valid_to IS NULL OR fc.valid_to = 'None' OR fc.valid_to >= ?)
    """, (prop_id, m_end, m_start))
    total = _ZERO
    for amt, freq, vf in rows:
        if freq == "monthly":
            total += amt
        elif freq == "annual":
            total += amt / 12
        elif freq == "one-time" and vf and vf[:7] == f"{y}-{m:02d}":
            total += amt
    return total


def _compute_snapshot(year: int, owner=None):
    """Return (snapshot, props) suitable for balance_sheet_pdf / the API,
    scoped to the given owner."""
    today = date.today()
    y = int(year)
    max_month = today.month if y == today.year else 12
    properties = fetch("SELECT id, name FROM properties WHERE owner_id=? ORDER BY name", (owner,))

    snap_start = str(today.replace(day=1))
    snap_end = str(today.replace(day=calendar.monthrange(today.year, today.month)[1]))
    snapshot = []
    for pid, pname in properties:
        exp = _expected_rent(pid, snap_start, snap_end)
        costs = _flat_costs_month(pid, snap_start, snap_end, today.year, today.month)
        snapshot.append({"name": pname, "expected": float(exp), "costs": float(costs), "net": float(exp - costs)})

    props = []
    for prop_id, prop_name in properties:
        rows = []
        tot_expected = tot_actual = tot_costs = _ZERO
        for m in range(1, max_month + 1):
            m_start = f"{y}-{m:02d}-01"
            m_end = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
            expected = _expected_rent(prop_id, m_start, m_end)
            actual = _actual_income(prop_id, m_start, m_end)
            costs = _flat_costs_month(prop_id, m_start, m_end, y, m)
            tot_expected += expected
            tot_actual += actual
            tot_costs += costs
            rows.append({
                "Month": date(y, m, 1).strftime("%b %Y"),
                "Expected rent (€)": round(expected, 2),
                "Actual received (€)": round(actual, 2),
                "Variance (€)": round(actual - expected, 2),
                "Costs (€)": round(costs, 2),
                "Expected net (€)": round(expected - costs, 2),
                "Actual net (€)": round(actual - costs, 2),
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
