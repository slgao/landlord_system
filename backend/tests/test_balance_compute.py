"""expected_rent / month_costs are pure: rows in, Decimal out."""
from decimal import Decimal

from balance_compute import expected_rent, month_costs

D = Decimal


def test_expected_rent_takes_latest_contract_per_apartment():
    # Two contracts overlap on apartment 1 (stale end_date on the old one):
    # only the most recently started counts. Apartment 2 adds its own rent.
    rows = [
        (1, D("500"), "2023-01-01", None, 1),
        (1, D("650"), "2025-03-01", None, 7),
        (2, D("400"), "2024-06-01", "2026-12-31", 3),
    ]
    assert expected_rent(rows, "2025-06-01", "2025-06-30") == D("1050")
    # Before the second contract started, the old one still counts.
    assert expected_rent(rows, "2025-01-01", "2025-01-31") == D("900")


def test_expected_rent_respects_end_dates_and_none_strings():
    rows = [
        (1, D("500"), "2024-01-01", "2024-12-31", 1),
        (2, D("300"), "2024-01-01", "None", 2),   # legacy 'None' text = open-ended
    ]
    assert expected_rent(rows, "2025-02-01", "2025-02-28") == D("300")
    assert expected_rent(rows, "2024-12-01", "2024-12-31") == D("800")
    assert expected_rent([], "2025-02-01", "2025-02-28") == D("0")


def test_month_costs_spreads_quarterly_and_annual_bills():
    rows = [
        (D("120"), "monthly", "2020-01-01", None),
        (D("300"), "quarterly", "2020-01-01", None),   # 100 / month
        (D("1200"), "annually", "2020-01-01", None),   # 100 / month
    ]
    assert month_costs(rows, "2025-05-01", "2025-05-31", 2025, 5) == D("320")


def test_month_costs_one_time_lands_in_its_month_only():
    rows = [(D("999"), "one-time", "2025-04-15", None)]
    assert month_costs(rows, "2025-04-01", "2025-04-30", 2025, 4) == D("999")
    assert month_costs(rows, "2025-05-01", "2025-05-31", 2025, 5) == D("0")


def test_month_costs_without_valid_from_is_always_in_force():
    # The old SQL compared valid_from <= month_end, which is NULL (false) for
    # a cost entered without a date — it silently vanished from the sheet.
    rows = [(D("50"), "monthly", None, None), (D("20"), "monthly", "None", None)]
    assert month_costs(rows, "2025-01-01", "2025-01-31", 2025, 1) == D("70")


def test_month_costs_validity_window():
    rows = [(D("10"), "monthly", "2025-03-10", "2025-05-02")]
    assert month_costs(rows, "2025-02-01", "2025-02-28", 2025, 2) == D("0")
    assert month_costs(rows, "2025-03-01", "2025-03-31", 2025, 3) == D("10")
    assert month_costs(rows, "2025-05-01", "2025-05-31", 2025, 5) == D("10")
    assert month_costs(rows, "2025-06-01", "2025-06-30", 2025, 6) == D("0")
