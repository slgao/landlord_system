"""Balance-sheet computations — no UI framework required.

These functions were extracted from the (removed) Streamlit page module so the
FastAPI reports router can compute the balance sheet without pulling in
Streamlit/pandas. Pure DB reads + arithmetic.
"""
import calendar
from datetime import date
from decimal import Decimal
from db import fetch

_ZERO = Decimal("0")


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


def _compute_snapshot(year: int):
    """Return (snapshot, props) suitable for balance_sheet_pdf / the API."""
    today = date.today()
    y = int(year)
    max_month = today.month if y == today.year else 12
    properties = fetch("SELECT id, name FROM properties ORDER BY name")

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
        })
    return snapshot, props
