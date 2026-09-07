"""expected_rent / month_costs are pure: rows in, Decimal out."""
from decimal import Decimal

import balance_compute
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


# ── The current month's share of the annuity ─────────────────────────────────
# The payment is constant; the interest inside it falls every month. These pin
# the split down, because it is the one figure a yearly total cannot show.

def _one_mortgage(monkeypatch, start="2020-01-01"):
    monkeypatch.setattr(balance_compute, "fetch",
                        lambda sql, params=(): [(100000, 3.0, 2.0, start)])


def test_month_split_sums_to_the_year_so_far(monkeypatch):
    from datetime import date
    _one_mortgage(monkeypatch)
    year = date.today().year
    fin = balance_compute._financing(1, 1, year)
    # Walk the year month by month via the same helper the report uses; the
    # months must add up to the year-so-far figures exactly.
    import tax_logic
    i_sum = t_sum = 0.0
    for m in range(1, date.today().month + 1):
        cur = tax_logic.annuity_year_breakdown(100000, 3.0, 2.0, "2020-01-01", year, m)
        prev = tax_logic.annuity_year_breakdown(100000, 3.0, 2.0, "2020-01-01", year, m - 1) if m > 1 else None
        i_sum += cur["interest"] - (prev["interest"] if prev else 0.0)
        t_sum += cur["tilgung"] - (prev["tilgung"] if prev else 0.0)
    assert round(i_sum, 2) == fin["interest_paid"]
    assert round(t_sum, 2) == fin["equity_paid"]
    # And the month itself is a real slice of the year, never the whole of it
    # (unless we happen to be in January).
    if date.today().month > 1:
        assert 0 < fin["interest_month"] < fin["interest_paid"]
        assert 0 < fin["equity_month"] < fin["equity_paid"]


def test_month_split_in_january_is_the_year_so_far(monkeypatch):
    # January has no earlier month to subtract; asking for month 0 would clamp
    # back to January and cancel the split to zero.
    from datetime import date
    import tax_logic
    monkeypatch.setattr(balance_compute, "date", type("D", (), {"today": staticmethod(lambda: date(2026, 1, 20))}))
    _one_mortgage(monkeypatch)
    fin = balance_compute._financing(1, 1, 2026)
    jan = tax_logic.annuity_year_breakdown(100000, 3.0, 2.0, "2020-01-01", 2026, 1)
    assert fin["interest_month"] == fin["interest_paid"] == round(jan["interest"], 2)
    assert fin["equity_month"] == fin["equity_paid"] == round(jan["tilgung"], 2)


def test_past_year_has_no_current_month(monkeypatch):
    from datetime import date
    _one_mortgage(monkeypatch)
    fin = balance_compute._financing(1, 1, date.today().year - 1)
    assert fin["interest_month"] is None and fin["equity_month"] is None
    assert fin["interest_paid"] > 0            # the completed year still reports
