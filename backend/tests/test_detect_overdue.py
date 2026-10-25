"""Tests for logic.detect_overdue — the payment-reminders core.

detect_overdue issues exactly ONE bundled DB round trip (active contracts and
payments grouped per contract per month, asked together). We monkeypatch
`logic.fetch_bundle` to route each part to canned rows, so these run without a
database. The model is a running
cumulative balance over a per-contract window, so the tests focus on that:
early payments and double payments net out, current-month payments are credit,
and `rent_settled_until` moves the window start.
"""
from datetime import date
import calendar

from decimal import Decimal

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


def _install_fetch(monkeypatch, contracts, payments, deposit=(), rents=None):
    """`payments` and `deposit` rows are (contract_id, 'YYYY-MM', amount): rent
    paid, and rent kept from the Kaution. The loader returns both in one
    UNION, tagged 0 / 1.

    `rents` is the agreed prices, as (contract_id, valid_from, rent) rows. Left
    out, each contract gets one price from its own tuple, running from the day
    the tenancy started — which is what a tenancy whose rent never changed
    looks like, and keeps these tests saying what they always said.

    Money crosses the bundle as TEXT (json_build_array would hand back floats,
    and rent arithmetic must stay Decimal), so the fake stringifies it exactly
    as `::text` does. `fetch` is left failing so an unbundled query added later
    shows up as a test failure rather than a silent extra round trip."""
    periods = (list(rents) if rents is not None
               else [(c[0], c[5], c[4]) for c in contracts])

    def fake_bundle(parts):
        names = [n for n, _, _ in parts]
        assert names == ["contracts", "paid", "rents"], f"unexpected bundle: {names}"
        return {
            # The contract row no longer carries a rent: the price of a month
            # comes from the periods below.
            # (id, tenant, email, apartment, start, end, property, currency,
            # settled, property_id) — the flat's property comes along because
            # the query already joins it, and the dashboard needs arrears per
            # property without a round trip of its own.
            "contracts": [(c[0], c[1], c[2], c[3], c[5], c[6], c[7], c[8], c[9], 1)
                          for c in contracts],
            "paid": ([(c, ym, 0, str(amt)) for c, ym, amt in payments]
                     + [(c, ym, 1, str(amt)) for c, ym, amt in deposit]),
            "rents": [(cid, vf, str(amount), None) for cid, vf, amount in periods],
        }

    def fail_fetch(query, params=()):
        raise AssertionError(f"unbundled query: {' '.join(query.split())}")

    monkeypatch.setattr(logic, "fetch_bundle", fake_bundle)
    monkeypatch.setattr(logic, "fetch", fail_fetch)


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


def test_unparsable_contract_dates_skip_only_that_contract(monkeypatch):
    # A legacy row with a broken start date used to raise ValueError and take
    # every other tenant's reminder down with it.
    broken = (2, "Bob", "b@x.de", "Apt 2", 500, "", None, "Haus A", "EUR", None)
    _install_fetch(monkeypatch, [_contract(), broken], [])
    res = logic.detect_overdue(default_months_back=3)
    assert [r["tenant"] for r in res] == ["Alice"]


# ── Rent kept from the deposit ────────────────────────────────────────────────
# Whether the tenant did not pay (Mietrückstand) or you agreed they could
# abwohnen, a Kaution deduction for rent is rent received on its date.

def test_rent_kept_from_deposit_clears_the_arrears(monkeypatch):
    cur = _cur_first()
    last = _add_months(cur, -1)
    _install_fetch(monkeypatch, [_contract()],
                   [(1, _ym(_add_months(cur, -3)), Decimal("700")),
                    (1, _ym(_add_months(cur, -2)), Decimal("700"))],
                   deposit=[(1, _ym(last), Decimal("700"))])
    assert logic.detect_overdue(default_months_back=3) == []


def test_partial_deposit_offset_is_shown_apart(monkeypatch):
    cur = _cur_first()
    _install_fetch(monkeypatch, [_contract()], [],
                   deposit=[(1, _ym(_add_months(cur, -1)), Decimal("500"))])
    [r] = logic.detect_overdue(default_months_back=3)
    assert r["paid_total"] == 500.0
    assert r["paid_from_deposit"] == 500.0
    assert r["amount_due"] == 1600.0


def test_each_row_says_which_property_the_arrears_belong_to(monkeypatch):
    """The dashboard needs arrears per property.

    It used to ask for the mapping afterwards, in a query of its own. This
    query already joins the flat, so it answers that too — one round trip
    instead of two, and no second place where a contract is matched to a flat.
    """
    cur = _cur_first()
    _install_fetch(monkeypatch, [_contract(start="2020-01-01")], [])
    res = logic.detect_overdue(default_months_back=2)
    assert res and res[0]["property_id"] == 1


# ── one row with an extreme date must not take the page down ────────────────

def test_a_contract_settled_to_the_end_of_time_is_simply_settled(monkeypatch):
    """`rent_settled_until = 9999-12-31` is a date the API accepts, and it
    says every month up to then is paid. Computing the window start from it
    overflowed the calendar and 500ed the whole page — for every tenancy, not
    just that one."""
    _install_fetch(monkeypatch, [_contract(settled="9999-12-31")], [])
    assert logic.detect_overdue(default_months_back=12) == []


def test_the_month_arithmetic_saturates_instead_of_raising():
    from datetime import date
    assert logic._add_months(date(9999, 12, 1), 1) == date(9999, 12, 1)
    assert logic._add_months(date(1, 1, 1), -1) == date(1, 1, 1)
    # and still shifts normally in between
    assert logic._add_months(date(2026, 1, 1), 13) == date(2027, 2, 1)
    assert logic._add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)


def test_one_extreme_row_does_not_hide_the_others(monkeypatch):
    # The point of the fix: the tenancy that is genuinely behind still shows.
    cur = _cur_first()
    behind = (2, "Bob", "b@x.de", "Apt 2", 700, "2020-01-01", None, "Haus A", "EUR", None)
    _install_fetch(monkeypatch, [_contract(settled="9999-12-31"), behind], [])
    res = logic.detect_overdue(default_months_back=3)
    assert [r["contract_id"] for r in res] == [2]
