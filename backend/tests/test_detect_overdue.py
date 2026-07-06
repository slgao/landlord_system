"""Tests for logic.detect_overdue — the payment-reminders core.

detect_overdue issues exactly two DB queries (active contracts, then payments
grouped per contract per month). We monkeypatch `logic.fetch` to route each
query to canned rows, so these run without a database. The model is a running
cumulative balance over a per-contract window, so the tests focus on that:
early payments and double payments net out, current-month payments are credit,
and `rent_settled_until` moves the window start.
"""
from datetime import date
import calendar

import logic


def _add_months(first, delta):
    idx = first.year * 12 + (first.month - 1) + delta
    y, m = divmod(idx, 12)
    return date(y, m + 1, 1)


def _cur_first():
    t = date.today()
    return date(t.year, t.month, 1)


def _ym(first):
    return first.strftime("%Y-%m")


def _month_end(first):
    return first.replace(day=calendar.monthrange(first.year, first.month)[1])


def _install_fetch(monkeypatch, contracts, payments):
    def fake_fetch(query, params=()):
        q = " ".join(query.split())
        if "FROM payments" in q and "GROUP BY" in q:
            return payments
        if "FROM contracts" in q and "JOIN tenants" in q:
            return contracts
        raise AssertionError(f"unexpected query: {q}")
    monkeypatch.setattr(logic, "fetch", fake_fetch)


# Active-contracts row shape:
# (id, tenant, email, apartment, rent, start, end, property, currency, settled)
def _contract(rent=700, start="2020-01-01", end=None, settled=None):
    return (1, "Alice", "a@x.de", "Apt 1", rent, start, end, "Haus A", "EUR", settled)


def test_all_months_unpaid_flagged(monkeypatch):
    _install_fetch(monkeypatch, [_contract()], [])          # no payments
    res = logic.detect_overdue(default_months_back=3)
    assert len(res) == 1
    r = res[0]
    assert r["property_name"] == "Haus A" and r["currency"] == "EUR"
    assert r["expected_total"] == 2100.0                     # 3 × 700
    assert r["paid_total"] == 0.0
    assert r["amount_due"] == 2100.0
    assert r["months_due"] == 3
    assert len(r["months"]) == 3


def test_double_payment_covers_previous_month(monkeypatch):
    # 2-month window; nothing in the first month, double rent in the second.
    prev1 = _add_months(_cur_first(), -1)
    payments = [(1, _ym(prev1), 1400)]                       # covers both months
    _install_fetch(monkeypatch, [_contract()], payments)
    assert logic.detect_overdue(default_months_back=2) == []  # nets to zero → not flagged


def test_early_payment_before_month_counts(monkeypatch):
    # Both months' rent paid up front in the earlier month.
    prev2 = _add_months(_cur_first(), -2)
    payments = [(1, _ym(prev2), 1400)]
    _install_fetch(monkeypatch, [_contract()], payments)
    assert logic.detect_overdue(default_months_back=2) == []


def test_current_month_payment_is_credit(monkeypatch):
    # Two complete months unpaid, but a catch-up payment lands this month.
    cur = _cur_first()
    payments = [(1, _ym(cur), 1400)]
    _install_fetch(monkeypatch, [_contract()], payments)
    assert logic.detect_overdue(default_months_back=2) == []


def test_partial_payment_leaves_balance(monkeypatch):
    prev1 = _add_months(_cur_first(), -1)
    payments = [(1, _ym(prev1), 700)]                        # only one of two months
    _install_fetch(monkeypatch, [_contract()], payments)
    r = logic.detect_overdue(default_months_back=2)[0]
    assert r["expected_total"] == 1400.0
    assert r["paid_total"] == 700.0
    assert r["amount_due"] == 700.0
    assert r["months_due"] == 1


def test_settled_until_clears_everything(monkeypatch):
    # Settle through the last complete month → window becomes empty → not flagged.
    end_first = _add_months(_cur_first(), -1)
    settled = str(_month_end(end_first))
    _install_fetch(monkeypatch, [_contract(settled=settled)], [])
    assert logic.detect_overdue(default_months_back=3) == []


def test_settled_until_partial_window(monkeypatch):
    # Settle through 2 months ago → only the most recent complete month is left.
    prev2 = _add_months(_cur_first(), -2)
    settled = str(_month_end(prev2))
    _install_fetch(monkeypatch, [_contract(settled=settled)], [])
    r = logic.detect_overdue(default_months_back=3)[0]
    assert len(r["months"]) == 1
    assert r["amount_due"] == 700.0
    assert r["first_month"] == r["last_month"]


def test_future_contract_not_flagged(monkeypatch):
    _install_fetch(monkeypatch, [_contract(start="2999-01-01")], [])
    assert logic.detect_overdue(default_months_back=3) == []


def test_ended_before_window_not_flagged(monkeypatch):
    _install_fetch(monkeypatch, [_contract(end="2000-01-01")], [])
    assert logic.detect_overdue(default_months_back=3) == []
