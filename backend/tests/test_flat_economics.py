"""What each flat earns.

The distinction these tests exist to protect: the Tilgung part of a mortgage
instalment is not a cost. A flat can be cashflow negative every month and still
be earning, and conflating the two makes a fast repayment look like a bad
investment.
"""
from decimal import Decimal

import pytest

from flat_economics import (contracted_rent, economics, portfolio_summary,
                            recurring_costs)

TODAY = "2026-10-24"


# ── Rent currently contracted ────────────────────────────────────────────────
# (apartment_id, rent, start, end, terminated, contract_id)

def test_a_running_contract_counts():
    rent, let = contracted_rent([(1, "738.00", "2025-01-01", None, 0, 10)], TODAY)
    assert rent == Decimal("738.00")
    assert let == {1: Decimal("738.00")}


def test_a_contract_that_has_not_started_does_not_count():
    rent, let = contracted_rent([(1, "738.00", "2027-01-01", None, 0, 10)], TODAY)
    assert rent == Decimal("0")
    assert let == {}


def test_an_expired_contract_does_not_count():
    rent, _ = contracted_rent([(1, "738.00", "2024-01-01", "2026-03-31", 0, 10)], TODAY)
    assert rent == Decimal("0")


def test_a_contract_ending_today_still_counts():
    rent, _ = contracted_rent([(1, "738.00", "2024-01-01", TODAY, 0, 10)], TODAY)
    assert rent == Decimal("738.00")


def test_a_terminated_contract_does_not_count_whatever_its_dates():
    rent, _ = contracted_rent([(1, "738.00", "2024-01-01", None, 1, 10)], TODAY)
    assert rent == Decimal("0")


def test_two_overlapping_contracts_on_one_room_pay_once():
    """A stale end_date on an old contract must not make a room pay twice —
    the same rule the balance sheet applies, and the reason it exists."""
    rent, let = contracted_rent([
        (1, "700.00", "2024-01-01", None, 0, 10),      # stale, never ended
        (1, "738.00", "2025-06-01", None, 0, 11),      # the real one
    ], TODAY)
    assert rent == Decimal("738.00")
    assert len(let) == 1


def test_the_rooms_of_a_wg_add_up():
    rent, let = contracted_rent([
        (1, "300.00", "2025-01-01", None, 0, 10),
        (2, "350.00", "2025-01-01", None, 0, 11),
        (3, "400.00", "2025-01-01", None, 0, 12),
    ], TODAY)
    assert rent == Decimal("1050.00")
    assert len(let) == 3


def test_a_room_with_no_contract_is_simply_absent():
    rent, let = contracted_rent([], TODAY)
    assert rent == Decimal("0") and let == {}


def test_a_contract_with_no_start_date_is_skipped():
    """A row that predates the date check must not be counted at an unknown
    time, nor take the page down."""
    rent, _ = contracted_rent([(1, "738.00", None, None, 0, 10)], TODAY)
    assert rent == Decimal("0")


# ── Recurring costs ──────────────────────────────────────────────────────────
# (amount, frequency, valid_from, valid_to)

def test_a_monthly_charge_is_itself():
    assert recurring_costs([("355.00", "monthly", "2024-01-01", None)], TODAY) == Decimal("355")


def test_a_quarterly_charge_is_spread_over_its_months():
    assert recurring_costs([("300.00", "quarterly", None, None)], TODAY) == Decimal("100")


def test_an_annual_charge_is_spread_over_the_year():
    assert recurring_costs([("1200.00", "annually", None, None)], TODAY) == Decimal("100")


def test_a_one_time_cost_is_not_a_recurring_charge():
    """It belongs to the month it was paid, not to every month."""
    assert recurring_costs([("5000.00", "one-time", "2026-03-01", None)], TODAY) == Decimal("0")


def test_a_superseded_price_is_not_added_to_its_successor():
    """Hausgeld raised from 355 to 358: only the row in force today counts, or
    the flat would appear to cost both."""
    rows = [("355.00", "monthly", "2024-01-01", "2026-06-30"),
            ("358.00", "monthly", "2026-07-01", None)]
    assert recurring_costs(rows, TODAY) == Decimal("358")


def test_a_charge_not_yet_in_force_does_not_count():
    assert recurring_costs([("358.00", "monthly", "2027-01-01", None)], TODAY) == Decimal("0")


def test_a_charge_with_no_dates_has_always_been_in_force():
    assert recurring_costs([("355.00", "monthly", None, None)], TODAY) == Decimal("355")


# ── The economics ────────────────────────────────────────────────────────────

def test_cashflow_is_rent_less_costs_less_the_whole_instalment():
    e = economics(rent=738, costs=355, instalment=412, interest=150)
    assert e["cashflow_monthly"] == pytest.approx(-29.0)


def test_the_operating_result_counts_only_the_interest():
    """The Tilgung buys the flat; it is saving, not spending. This flat is
    cashflow negative and still earning 233 € a month."""
    e = economics(rent=738, costs=355, instalment=412, interest=150)
    assert e["operating_monthly"] == pytest.approx(233.0)
    assert e["principal_monthly"] == pytest.approx(262.0)
    assert e["cashflow_monthly"] < 0 < e["operating_monthly"]


def test_interest_is_never_counted_above_the_instalment():
    """A guard, not a scenario: it would make the Tilgung negative."""
    e = economics(rent=738, costs=0, instalment=100, interest=250)
    assert e["interest_monthly"] == 100.0
    assert e["principal_monthly"] == 0.0


def test_the_yields_come_off_the_value():
    e = economics(rent=1000, costs=200, value=240_000)
    assert e["gross_yield"] == pytest.approx(5.0)       # 12.000 / 240.000
    assert e["net_yield"] == pytest.approx(4.0)         # 9.600 / 240.000


def test_the_kaufpreisfaktor_is_the_price_to_rent_multiple():
    e = economics(rent=1000, costs=200, value=240_000)
    assert e["kaufpreisfaktor"] == pytest.approx(20.0)


def test_a_flat_with_no_value_still_has_a_cashflow():
    """Withholding the whole row because a valuation is missing would hide the
    figure that needs no valuation at all."""
    e = economics(rent=738, costs=355, instalment=412, interest=150, value=None)
    assert e["cashflow_monthly"] == pytest.approx(-29.0)
    assert e["gross_yield"] is None
    assert e["kaufpreisfaktor"] is None
    assert e["equity_return"] is None


def test_the_equity_return_counts_the_tilgung_as_the_saving_it_is():
    # equity 100.000; (operating 233 + principal 262) × 12 / 100.000
    e = economics(rent=738, costs=355, instalment=412, interest=150,
                  value=300_000, debt=200_000)
    assert e["equity_return"] == pytest.approx((233 + 262) * 12 / 100_000 * 100, abs=0.05)


def test_no_equity_return_when_the_debt_exceeds_the_value():
    e = economics(rent=738, costs=355, value=100_000, debt=130_000)
    assert e["equity_return"] is None


def test_a_rent_free_flat_has_no_kaufpreisfaktor():
    """Dividing by a rent of zero is the one thing that would raise here."""
    e = economics(rent=0, costs=355, value=240_000)
    assert e["kaufpreisfaktor"] is None
    assert e["gross_yield"] == 0.0


def test_occupancy_counts_let_rooms_against_rooms():
    e = economics(rent=1050, costs=0, rooms=3, let_rooms=2)
    assert e["vacant_rooms"] == 1
    assert e["occupancy"] == pytest.approx(66.7, abs=0.1)


def test_a_flat_with_no_rooms_has_no_occupancy():
    assert economics(rent=0, costs=0, rooms=0, let_rooms=0)["occupancy"] is None


def test_arrears_are_carried_through():
    assert economics(rent=738, costs=0, arrears=1476.0)["arrears"] == 1476.0


# ── The portfolio ────────────────────────────────────────────────────────────

def _flat(rent, costs, inst=0.0, interest=0.0, value=None, rooms=1, let=1):
    return economics(rent=rent, costs=costs, instalment=inst, interest=interest,
                     value=value, rooms=rooms, let_rooms=let) | {"value": value}


def test_the_summary_adds_the_flats_up():
    s = portfolio_summary([_flat(738, 355, 412, 150, 300_000),
                           _flat(606, 200, 0, 0, 250_000)])
    assert s["flats"] == 2
    assert s["rent_monthly"] == pytest.approx(1344.0)
    assert s["costs_monthly"] == pytest.approx(555.0)
    assert s["cashflow_monthly"] == pytest.approx(377.0)
    assert s["value"] == pytest.approx(550_000.0)


def test_the_summary_yield_is_weighted_by_value_not_averaged():
    """An average of percentages weights a studio the same as a house."""
    s = portfolio_summary([_flat(1000, 0, value=100_000),    # 12 %
                           _flat(1000, 0, value=900_000)])   # 1,33 %
    assert s["gross_yield"] == pytest.approx(24_000 / 1_000_000 * 100, abs=0.01)
    assert s["gross_yield"] != pytest.approx((12.0 + 1.33) / 2, abs=0.5)


def test_a_flat_without_a_value_does_not_drag_the_yield_down():
    """Its rent would otherwise be divided by a value that excludes it."""
    s = portfolio_summary([_flat(1000, 0, value=240_000), _flat(1000, 0, value=None)])
    assert s["valued_flats"] == 1
    assert s["gross_yield"] == pytest.approx(5.0)
    # The cashflow still covers both — it needs no valuation.
    assert s["rent_monthly"] == pytest.approx(2000.0)


def test_an_empty_portfolio_has_no_summary():
    assert portfolio_summary([]) is None


def test_the_summary_occupancy_spans_every_room():
    s = portfolio_summary([_flat(300, 0, rooms=3, let=2), _flat(700, 0, rooms=1, let=1)])
    assert s["rooms"] == 4 and s["let_rooms"] == 3
    assert s["occupancy"] == pytest.approx(75.0)


# ── The mortgage recorded twice ──────────────────────────────────────────────
# Five flats here record the instalment BOTH as a "Mortgage" flat cost and as a
# loan in the mortgages table. Counting both subtracted it twice and made every
# mortgaged flat look like it was bleeding money.

from flat_economics import is_mortgage_cost, split_costs       # noqa: E402

COSTS = [("Hausgeld", "358.00", "monthly", None, None),
         ("Grundsteuer", "32.76", "monthly", None, None),
         ("Mortgage", "641.84", "monthly", None, None),
         ("Internet", "45.00", "monthly", None, None)]


@pytest.mark.parametrize("name", ["Mortgage", "mortgage", " MORTGAGE ", "Hypothek",
                                  "Darlehen", "Annuität", "Annuitaet", "Kredit",
                                  "Mortgage (Bank)"])
def test_the_ways_a_mortgage_cost_is_named(name):
    assert is_mortgage_cost(name) is True


@pytest.mark.parametrize("name", ["Hausgeld", "Grundsteuer", "Internet", "Rundfunk",
                                  "Miete", "Verwaltungsbetreuung", "", None])
def test_a_running_cost_is_not_a_mortgage(name):
    assert is_mortgage_cost(name) is False


def test_the_mortgage_is_split_out_of_the_running_costs():
    running, mortgage = split_costs(COSTS, TODAY)
    assert running == Decimal("435.76")        # 358 + 32,76 + 45
    assert mortgage == Decimal("641.84")


def test_a_flat_with_no_mortgage_cost_splits_to_zero():
    running, mortgage = split_costs(COSTS[:2] + COSTS[3:], TODAY)
    assert mortgage == Decimal("0")
    assert running == Decimal("435.76")


def test_the_cashflow_is_unchanged_by_the_reclassification():
    """The money leaving the account is the same; only its label moves. This is
    the invariant the fix had to preserve."""
    running, mortgage = split_costs(COSTS, TODAY)
    before = 1400 - float(recurring_costs(COSTS, TODAY)) - 0          # all as cost
    after = economics(rent=1400, costs=running,
                      instalment=float(mortgage), interest=150)["cashflow_monthly"]
    assert after == pytest.approx(before)


def test_an_instalment_without_loan_terms_leaves_the_split_unknown():
    """One flat records the mortgage only as a cost, with no loan on file. The
    cashflow is still exact; how much of the payment is interest is not
    knowable, and is not guessed."""
    e = economics(rent=1798, costs=740, instalment=656.74, interest=None)
    assert e["cashflow_monthly"] == pytest.approx(401.26)
    assert e["split_known"] is False
    assert e["interest_monthly"] is None
    assert e["principal_monthly"] is None
    assert e["operating_monthly"] is None
    assert e["equity_return"] is None


def test_a_flat_with_no_mortgage_at_all_has_a_known_split():
    """Nothing is unknown about a flat that owes nothing."""
    e = economics(rent=950, costs=627, instalment=0.0, interest=0.0)
    assert e["split_known"] is True
    assert e["operating_monthly"] == pytest.approx(323.0)


def test_the_summary_counts_how_many_splits_are_unknown():
    known = economics(rent=1400, costs=436, instalment=644, interest=150) | {"value": None}
    unknown = economics(rent=1798, costs=740, instalment=657, interest=None) | {"value": None}
    s = portfolio_summary([known, unknown])
    assert s["split_unknown"] == 1
    # The unknown flat's interest counts as nothing, so the operating total is
    # a floor rather than an exact figure — which is what split_unknown says.
    assert s["operating_monthly"] == pytest.approx(1400 + 1798 - 436 - 740 - 150)
