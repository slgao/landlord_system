"""Tests for logic.detect_overdue — the payment-reminders core.

detect_overdue issues exactly two DB queries (active contracts, then payments
grouped per contract per month). We monkeypatch `logic.fetch` to route each
query to canned rows, so these run without a database and pin down both the
overdue math and the N+1 rewrite (payments come from the grouped dict, not a
per-month query).
"""
from datetime import date
from decimal import Decimal

import logic


def _checked_months(months_back):
    """Replicate detect_overdue's month window (oldest first, current month
    excluded) so tests can target specific months deterministically."""
    today = date.today()
    out = []
    for i in range(months_back, 0, -1):
        m, y = today.month - i, today.year
        while m <= 0:
            m += 12
            y -= 1
        out.append(date(y, m, 1))
    return out


def _install_fetch(monkeypatch, contracts, payments):
    def fake_fetch(query, params=()):
        q = " ".join(query.split())
        if "FROM payments" in q and "GROUP BY" in q:
            return payments
        if "FROM contracts" in q and "JOIN tenants" in q:
            return contracts
        raise AssertionError(f"unexpected query: {q}")
    monkeypatch.setattr(logic, "fetch", fake_fetch)


# Contract row shape returned by the active-contracts query:
# (id, tenant, email, apartment, rent, start_date, end_date, property, currency)
def _contract(rent="700", start="2020-01-01", end=None, currency="EUR"):
    return (1, "Alice", "a@x.de", "Apt 1", Decimal(rent), start, end, "Haus A", currency)


def test_all_months_unpaid(monkeypatch):
    _install_fetch(monkeypatch, [_contract()], [])   # no payments at all
    res = logic.detect_overdue(months_back=3)
    assert len(res) == 1
    r = res[0]
    assert r["tenant"] == "Alice"
    assert r["property_name"] == "Haus A"      # enriched, no extra query
    assert r["currency"] == "EUR"
    assert len(r["overdue_months"]) == 3
    assert r["total_due"] == 2100.0            # 700 × 3
    assert all(m["gap"] == 700.0 and m["paid"] == 0.0 for m in r["overdue_months"])


def test_fully_paid_month_excluded(monkeypatch):
    months = _checked_months(3)
    paid_ym = months[-1].strftime("%Y-%m")     # newest checked month paid in full
    payments = [(1, paid_ym, Decimal("700"))]
    _install_fetch(monkeypatch, [_contract()], payments)
    res = logic.detect_overdue(months_back=3)
    r = res[0]
    assert len(r["overdue_months"]) == 2
    assert months[-1].strftime("%B %Y") not in [m["month"] for m in r["overdue_months"]]
    assert r["total_due"] == 1400.0


def test_partial_payment_leaves_gap(monkeypatch):
    ym = _checked_months(1)[0].strftime("%Y-%m")
    payments = [(1, ym, Decimal("300"))]
    _install_fetch(monkeypatch, [_contract()], payments)
    res = logic.detect_overdue(months_back=1)
    m = res[0]["overdue_months"][0]
    assert m["paid"] == 300.0
    assert m["gap"] == 400.0                    # 700 − 300


def test_fully_paid_contract_absent(monkeypatch):
    payments = [(1, mo.strftime("%Y-%m"), Decimal("700")) for mo in _checked_months(3)]
    _install_fetch(monkeypatch, [_contract()], payments)
    assert logic.detect_overdue(months_back=3) == []


def test_contract_starting_in_future_skipped(monkeypatch):
    _install_fetch(monkeypatch, [_contract(start="2999-01-01")], [])
    assert logic.detect_overdue(months_back=3) == []


def test_terminated_end_date_before_window_skipped(monkeypatch):
    _install_fetch(monkeypatch, [_contract(end="2000-01-01")], [])
    assert logic.detect_overdue(months_back=3) == []
