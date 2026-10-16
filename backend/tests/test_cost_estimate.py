"""Estimating what a meter's consumption costs over a period.

Consumption comes from the meter's own readings; the tariff is the
Arbeitspreis per unit plus the Grundpreis for the days in the period. A bound
nobody read is derived, and the answer says so — that is the difference
between a calculation and an estimate.
"""
import pytest

from logic import estimate_utility_cost, reading_on

# A meter read on the first of three months, running 100 units a month.
SERIES = [("2026-01-01", 1000.0), ("2026-02-01", 1100.0), ("2026-03-01", 1200.0)]


# ── reading on a date ────────────────────────────────────────────────────────

def test_a_date_that_was_read_is_measured():
    assert reading_on(SERIES, "2026-02-01") == (1100.0, "measured")


def test_a_date_between_readings_is_interpolated():
    value, source = reading_on(SERIES, "2026-01-16")
    assert source == "interpolated"
    assert round(value, 1) == 1048.4          # 15 of 31 days into the month


def test_a_date_past_the_last_reading_is_extrapolated():
    value, source = reading_on(SERIES, "2026-04-01")
    assert source == "extrapolated"
    # 200 units over 59 days, carried 31 days past the last reading
    assert round(value) == round(1200 + 200 / 59 * 31)


def test_a_date_before_the_first_reading_is_extrapolated():
    value, source = reading_on(SERIES, "2025-12-01")
    assert source == "extrapolated"
    assert value < 1000.0


def test_a_single_reading_cannot_be_interpolated():
    assert reading_on([("2026-01-01", 500.0)], "2026-01-01") == (500.0, "measured")
    assert reading_on([("2026-01-01", 500.0)], "2026-06-01") == (500.0, "extrapolated")


def test_no_readings_says_so():
    assert reading_on([], "2026-01-01") == (None, "no_readings")


# ── the cost ─────────────────────────────────────────────────────────────────

def test_arbeitspreis_times_consumption_plus_the_grundpreis():
    out = estimate_utility_cost(SERIES, "2026-01-01", "2026-03-01",
                                arbeitspreis=0.35, grundpreis_monthly=12.0)
    assert out["consumption"] == 200.0
    assert out["days"] == 60                      # inclusive of both days
    assert out["arbeitskosten"] == 70.0           # 200 × 0.35
    assert out["grundkosten"] == round(12 * 12 / 365 * 60, 2)
    assert out["total"] == round(70.0 + 12 * 12 / 365 * 60, 2)
    assert out["estimated"] is False              # both bounds were read


def test_gas_is_metered_in_m3_and_billed_in_kwh():
    # 200 m³ × Zustandszahl 0.95 × Brennwert 11.5 = 2185 kWh
    out = estimate_utility_cost(SERIES, "2026-01-01", "2026-03-01",
                                arbeitspreis=0.11, conversion_factor=0.95 * 11.5)
    assert out["billed_units"] == 2185.0
    assert out["arbeitskosten"] == round(2185 * 0.11, 2)


def test_a_derived_bound_marks_the_answer_as_an_estimate():
    out = estimate_utility_cost(SERIES, "2026-01-01", "2026-04-01", arbeitspreis=0.35)
    assert out["end_source"] == "extrapolated"
    assert out["estimated"] is True


def test_the_grundpreis_alone_still_costs_money():
    out = estimate_utility_cost(SERIES, "2026-01-01", "2026-01-01",
                                arbeitspreis=0.35, grundpreis_monthly=12.0)
    assert out["consumption"] == 0.0
    assert out["days"] == 1
    assert out["total"] == round(12 * 12 / 365, 2)


def test_a_backwards_period_is_refused():
    with pytest.raises(ValueError):
        estimate_utility_cost(SERIES, "2026-03-01", "2026-01-01", arbeitspreis=0.35)


def test_a_meter_without_readings_cannot_be_estimated():
    assert estimate_utility_cost([], "2026-01-01", "2026-03-01",
                                 arbeitspreis=0.35) == {"readings": 0, "source": "no_readings"}


def test_the_monthly_figure_is_the_period_scaled_to_a_month():
    out = estimate_utility_cost(SERIES, "2026-01-01", "2026-03-01",
                                arbeitspreis=0.35, grundpreis_monthly=12.0)
    assert out["per_month"] == round(out["total"] / out["days"] * 365 / 12, 2)


# ── A meter that runs backwards ───────────────────────────────────────────────
# Real portfolio data has a gas meter reading 788.75 one month and 788.00 the
# next: the meter was exchanged, or a digit was mistyped. Subtracting those
# gives a negative consumption, and a negative consumption × a tariff is a
# negative Arbeitskosten that quietly discounts the bill. The figures still
# come back — seeing them is how the bad reading gets found — but flagged.

BACKWARDS = [("2026-07-02", 788.75), ("2026-08-19", 788.00)]


def test_a_falling_meter_count_is_flagged():
    out = estimate_utility_cost(BACKWARDS, "2026-07-02", "2026-08-19",
                                arbeitspreis=0.12, grundpreis_monthly=10.0)
    assert out["consumption"] < 0
    assert out["decreasing"] is True


def test_a_rising_meter_count_is_not_flagged():
    out = estimate_utility_cost(SERIES, "2026-01-01", "2026-03-01", arbeitspreis=0.35)
    assert out["consumption"] > 0
    assert out["decreasing"] is False


def test_an_unchanged_meter_is_not_flagged():
    """Nothing consumed is not the same as a meter running backwards."""
    out = estimate_utility_cost([("2026-01-01", 500.0), ("2026-03-01", 500.0)],
                                "2026-01-01", "2026-03-01", arbeitspreis=0.35)
    assert out["consumption"] == 0.0
    assert out["decreasing"] is False
