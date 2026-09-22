"""Nebenkostenabrechnungen to tenants: the §556 deadline, what counts as
covered, open/settled, payment validation, and where the money lands in the
tax report."""
from datetime import date

import pytest
from pydantic import ValidationError

import nk_settlement_logic as logic
from api.schemas.payment import PaymentIn


# ── §556 Abs. 3 deadline ──────────────────────────────────────────────────────

@pytest.mark.parametrize("period_end, deadline", [
    (date(2025, 12, 31), date(2026, 12, 31)),     # calendar year
    (date(2025, 6, 30), date(2026, 6, 30)),       # off-calendar period
    (date(2024, 2, 29), date(2025, 2, 28)),       # leap day carries to month end
    (date(2023, 2, 28), date(2024, 2, 29)),       # month end stays month end
    (date(2025, 3, 15), date(2026, 3, 15)),       # mid-month
])
def test_deadline_is_twelve_months_after_the_period(period_end, deadline):
    assert logic.abrechnung_deadline(period_end) == deadline


# ── open / partial / settled ──────────────────────────────────────────────────

def test_nachzahlung_states():
    assert logic.settlement_state(180, 0) == (180.0, "open")
    assert logic.settlement_state(180, 100) == (80.0, "partial")
    assert logic.settlement_state(180, 180) == (0.0, "settled")


def test_guthaben_is_settled_by_a_negative_payment():
    assert logic.settlement_state(-95, 0) == (-95.0, "open")
    assert logic.settlement_state(-95, -95) == (0.0, "settled")


def test_rounding_noise_does_not_leave_a_cent_open():
    assert logic.settlement_state(100.10, 100.1000001)[1] == "settled"


# ── which years still need an Abrechnung ──────────────────────────────────────

TODAY = date(2026, 9, 22)


def _c(cid, start, end=None, nk=150, tenant=1, apt=1):
    return (cid, tenant, apt, start, end, nk)


def test_last_year_is_due_with_the_days_left():
    out = logic.pending_abrechnungen([_c(1, "2024-06-01")], [], TODAY)
    [row] = out                                  # 2024's deadline is long past
    assert row["year"] == 2025
    assert row["deadline"] == "2026-12-31"
    assert row["days_remaining"] == 100
    assert row["level"] == "due"


def test_recorded_settlement_clears_the_year():
    out = logic.pending_abrechnungen(
        [_c(1, "2024-06-01")], [(1, "2025-01-01", "2025-12-31")], TODAY)
    assert out == []


def test_an_off_calendar_period_overlapping_the_year_covers_it():
    out = logic.pending_abrechnungen(
        [_c(1, "2024-06-01")], [(1, "2025-07-01", "2026-06-30")], TODAY)
    assert out == []


def test_a_recently_missed_deadline_shows_as_missed():
    today = date(2027, 1, 20)
    out = logic.pending_abrechnungen([_c(1, "2025-03-01")], [], today)
    missed = [r for r in out if r["year"] == 2025]
    assert missed and missed[0]["level"] == "missed"
    assert missed[0]["days_remaining"] == -20


def test_no_prepayment_means_nothing_to_settle():
    assert logic.pending_abrechnungen([_c(1, "2024-01-01", nk=None)], [], TODAY) == []
    assert logic.pending_abrechnungen([_c(1, "2024-01-01", nk=0)], [], TODAY) == []


def test_a_tenant_who_moved_out_mid_year_still_gets_one():
    out = logic.pending_abrechnungen([_c(1, "2023-01-01", "2025-04-30")], [], TODAY)
    assert [r["year"] for r in out] == [2025]


def test_a_contract_starting_this_year_has_nothing_due_yet():
    assert logic.pending_abrechnungen([_c(1, "2026-02-01")], [], TODAY) == []


def test_a_follow_on_contract_is_one_tenancy():
    # Rent raise via Nachtrag: two contracts, same tenant and flat. One
    # reminder, pointing at the contract running at the end of the year, and
    # a settlement on either contract covers both.
    contracts = [_c(1, "2024-01-01", "2025-05-31"), _c(2, "2025-06-01")]
    [row] = logic.pending_abrechnungen(contracts, [], TODAY)
    assert row["contract_id"] == 2
    assert logic.pending_abrechnungen(contracts, [(1, "2025-01-01", "2025-12-31")], TODAY) == []


def test_different_tenants_in_one_flat_are_separate():
    contracts = [_c(1, "2024-01-01", "2025-05-31", tenant=1),
                 _c(2, "2025-06-01", tenant=2)]
    out = logic.pending_abrechnungen(contracts, [(2, "2025-06-01", "2025-12-31")], TODAY)
    assert [(r["contract_id"], r["year"]) for r in out] == [(1, 2025)]


# ── payment validation ────────────────────────────────────────────────────────

def _pay(**kw):
    return PaymentIn(**{"contract_id": 1, "amount": 100, "payment_date": "2026-01-05", **kw})


def test_rent_is_the_default_kind():
    assert _pay().kind == "rent"


def test_a_refund_is_a_negative_settlement_payment():
    p = _pay(kind="nk_settlement", amount=-95, settlement_id=3)
    assert p.amount == -95 and p.settlement_id == 3


def test_negative_rent_is_refused():
    with pytest.raises(ValidationError):
        _pay(amount=-100)


def test_rent_cannot_be_linked_to_a_settlement():
    with pytest.raises(ValidationError):
        _pay(settlement_id=3)


def test_zero_is_refused():
    with pytest.raises(ValidationError):
        _pay(amount=0)


def test_unknown_kind_is_refused():
    with pytest.raises(ValidationError):
        _pay(kind="deposit")


# ── tax report: settlements are Umlagen, and never decide the income source ──

def _tax_books(monkeypatch, payments, nk=100.0):
    """One property, one contract running all of 2025 at 1000 warm incl.
    `nk` NK prepayment. `payments` rows are (kind, total, count)."""
    from api.routers import tax

    def fake_fetch(sql, params=()):
        q = " ".join(sql.split())
        if "FROM properties" in q:
            return [(1, "Haus A", 1)]
        if "FROM payments" in q:
            return [(1, kind, total, cnt) for kind, total, cnt in payments]
        if "FROM contracts" in q:
            return [(1, "Mieter", 1000.0, "2025-01-01", None, nk)]
        return []
    monkeypatch.setattr(tax, "fetch", fake_fetch)
    monkeypatch.setattr(tax, "list_expenses", lambda year, owner: [])
    blocks, _ = tax.build_report(2025, 1)
    return blocks[0]["income"]


def test_settlement_lands_on_the_umlagen_line(monkeypatch):
    inc = _tax_books(monkeypatch, [("rent", 12000.0, 12), ("nk_settlement", 180.0, 1)])
    assert inc["final"] == 12180.0
    assert inc["umlagen"] == 1380.0            # 12 × 100 prepaid + 180 Nachzahlung
    assert inc["kaltmiete"] == 10800.0         # untouched by the settlement
    assert inc["nk_settlements"] == 180.0
    assert inc["payments_count"] == 12


def test_a_refund_reduces_umlagen(monkeypatch):
    inc = _tax_books(monkeypatch, [("rent", 12000.0, 12), ("nk_settlement", -95.0, 1)])
    assert inc["final"] == 11905.0
    assert inc["umlagen"] == 1105.0
    assert inc["kaltmiete"] == 10800.0


def test_a_lone_settlement_does_not_replace_the_rent_estimate(monkeypatch):
    # No rent recorded: income stays the contract estimate, plus the settlement —
    # not "180 € from payments" as the whole year.
    inc = _tax_books(monkeypatch, [("nk_settlement", 180.0, 1)])
    assert inc["source"] == "estimate"
    assert inc["final"] == 12180.0


def test_a_nachzahlung_kept_from_the_deposit_is_umlagen_too(monkeypatch):
    # The deduction arrives in the same UNION as the settlement payments,
    # as a second nk_settlement row for the property; both must add up.
    inc = _tax_books(monkeypatch, [("rent", 12000.0, 12), ("nk_settlement", 100.0, 1),
                                   ("nk_settlement", 150.0, 1)])
    assert inc["nk_settlements"] == 250.0
    assert inc["umlagen"] == 1450.0
    assert inc["kaltmiete"] == 10800.0



def test_rent_kept_from_the_deposit_is_income_when_rent_is_recorded(monkeypatch):
    inc = _tax_books(monkeypatch, [("rent", 11000.0, 11), ("deposit_rent", 1000.0, 1)])
    assert inc["final"] == 12000.0
    assert inc["rent_from_deposit"] == 1000.0
    assert inc["kaltmiete"] == 10800.0            # it is rent, so it lands in the Kaltmiete


def test_rent_kept_from_the_deposit_is_not_added_to_the_estimate(monkeypatch):
    # No rent recorded: the estimate already counts every contract month.
    inc = _tax_books(monkeypatch, [("deposit_rent", 1000.0, 1)])
    assert inc["source"] == "estimate"
    assert inc["final"] == 12000.0
    assert inc["rent_from_deposit"] == 0.0


# ── Pauschale / Warmmiete: nothing to settle ──────────────────────────────────

def test_a_flat_rate_contract_owes_no_abrechnung():
    flat = (1, 1, 1, "2024-06-01", None, 150, "flat")
    assert logic.pending_abrechnungen([flat], [], TODAY) == []


def test_prepayment_is_the_default_when_the_mode_is_absent():
    # Rows without the mode column keep the old behaviour.
    assert [r["year"] for r in logic.pending_abrechnungen([_c(1, "2024-06-01")], [], TODAY)] == [2025]


def test_switching_to_a_pauschale_ends_the_obligation():
    # Prepayment until March 2025, then a follow-on contract on a Pauschale:
    # 2025 still needs an Abrechnung for Jan–Mar, pointed at the prepayment one.
    contracts = [(1, 1, 1, "2024-01-01", "2025-03-31", 150, "prepayment"),
                 (2, 1, 1, "2025-04-01", None, 150, "flat")]
    [row] = logic.pending_abrechnungen(contracts, [], TODAY)
    assert (row["year"], row["contract_id"]) == (2025, 1)


# ── Provider bills on expenses ────────────────────────────────────────────────

def _exp(**kw):
    from api.routers.tax import ExpenseIn
    return ExpenseIn(**{"property_id": 1, "expense_date": "2026-03-01", "amount": 120.0,
                        "category": "Versorgerabrechnung", **kw})


def test_a_provider_bill_needs_its_period():
    with pytest.raises(ValidationError):
        _exp(utility="strom")
    b = _exp(utility="strom", period_start="2025-01-01", period_end="2025-12-31", bill_total=980.0)
    assert b.utility == "strom" and b.bill_total == 980.0


def test_bill_period_must_run_forwards():
    with pytest.raises(ValidationError):
        _exp(utility="gas", period_start="2025-12-31", period_end="2025-01-01")


def test_unknown_utility_is_refused():
    with pytest.raises(ValidationError):
        _exp(utility="internet", period_start="2025-01-01", period_end="2025-12-31")


def test_a_plain_expense_edit_does_not_touch_bill_fields():
    # The Tax Setup form sends none of them; update_expense writes only
    # fields that were sent, so saving there cannot wipe a bill's period.
    from api.routers.tax import _BILL_FIELDS
    plain = _exp()
    assert not set(_BILL_FIELDS) & plain.model_fields_set
