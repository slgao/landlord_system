"""The balance sheet takes the mortgage from whichever record exists.

It used to take it only from a `Mortgage` flat-cost row while the flat
economics took it from the loan — so where the two disagreed, the two pages
disagreed. The rule now lives in cost_types and both import it.

The case these tests mostly guard is the landlord who has entered the flat's
costs but not yet the loan's terms: the mortgage must still be charged.
"""
from decimal import Decimal

import pytest

from balance_compute import loan_instalment

TODAY = "2026-10-24"

# (principal, interest_rate_pct, tilgung_rate_pct, start, fixed_until, follow_up)
MHYP = (Decimal("125000"), Decimal("1.42"), Decimal("3.0"), "2019-11-30", None, None)
KFW = (Decimal("50000"), Decimal("0.37"), Decimal("3.9747"), "2020-10-31", None, None)


def test_an_annuity_is_principal_times_zins_plus_tilgung():
    assert loan_instalment([MHYP], TODAY) == pytest.approx(Decimal("460.42"), abs=0.01)


def test_several_loans_on_one_flat_add_up():
    assert loan_instalment([MHYP, KFW], TODAY) == pytest.approx(Decimal("641.45"), abs=0.01)


def test_a_loan_signed_but_not_yet_drawn_costs_nothing():
    future = (Decimal("100000"), Decimal("3.0"), Decimal("2.0"), "2030-01-01", None, None)
    assert loan_instalment([future], TODAY) == Decimal("0")


def test_a_loan_starting_today_is_already_being_serviced():
    today_loan = (Decimal("100000"), Decimal("3.0"), Decimal("2.0"), TODAY, None, None)
    assert loan_instalment([today_loan], TODAY) > 0


def test_a_loan_long_since_paid_off_costs_nothing():
    """A 10-year-old loan at 5 % Tilgung finished years ago; charging it still
    would make a flat look permanently more expensive than it is."""
    old = (Decimal("50000"), Decimal("2.0"), Decimal("20.0"), "2010-01-01", None, None)
    assert loan_instalment([old], TODAY) == Decimal("0")


def test_an_interest_only_loan_never_pays_off_and_keeps_costing():
    """A Bauspar-Vorausdarlehen: interest only, balance flat until Zuteilung."""
    vorausdarlehen = (Decimal("43329"), Decimal("2.06"), Decimal("0"), "2022-04-01", None, None)
    assert loan_instalment([vorausdarlehen], TODAY) == pytest.approx(
        Decimal("74.38"), abs=0.5)


def test_a_loan_with_no_start_date_is_skipped_rather_than_charged_at_an_unknown_time():
    broken = (Decimal("100000"), Decimal("3.0"), Decimal("2.0"), None, None, None)
    assert loan_instalment([broken], TODAY) == Decimal("0")


def test_no_loans_means_no_instalment():
    assert loan_instalment([], TODAY) == Decimal("0")
