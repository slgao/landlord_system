"""The history of one flat or WG room.

What is measured here is the part no other view computes: how much of the time
a unit actually earned, and how long it stood empty. Those figures are only
worth showing if they cannot be inflated — by a tenancy that has not begun, by
the same weeks counted twice, or by a gap that happens to fall after the last
tenant instead of between two of them.
"""
from datetime import date

from rent_periods import RentSchedule
from tenancy_history import CURRENT, PAST, UPCOMING, build, months_running, status_of

TODAY = date(2026, 11, 28)


def tenancy(contract_id=1, tenant="A", start="2025-01-01", end=None,
            terminated=0, rents=(("2025-01-01", 500, 100),), **extra):
    row = {"contract_id": contract_id, "tenant_id": contract_id,
           "tenant_name": tenant, "start_date": start, "end_date": end,
           "terminated": terminated, "schedule": RentSchedule(rents)}
    row.update(extra)
    return row


def summary_of(*tenancies):
    return build(list(tenancies), TODAY)["summary"]


# ── status: the end date draws the timeline, the flag only says if it is live ──

def test_a_term_that_has_run_out_is_past_even_without_the_terminated_flag():
    assert status_of(date(2024, 1, 1), date(2025, 6, 30), False, TODAY) == PAST


def test_an_open_tenancy_marked_terminated_is_over():
    assert status_of(date(2024, 1, 1), None, True, TODAY) == PAST


def test_an_open_tenancy_not_marked_terminated_is_running():
    assert status_of(date(2024, 1, 1), None, False, TODAY) == CURRENT


def test_an_end_date_in_the_future_is_still_a_running_tenancy():
    assert status_of(date(2024, 1, 1), date(2027, 3, 31), False, TODAY) == CURRENT


def test_a_term_that_has_not_begun_is_upcoming():
    assert status_of(date(2027, 1, 1), None, False, TODAY) == UPCOMING


# ── length: calendar months, the convention rent is owed in ────────────────

def test_a_year_to_the_day_before_the_anniversary_is_twelve_months():
    assert months_running(date(2025, 9, 1), date(2026, 8, 31)) == 12


def test_one_day_into_a_month_owes_that_month_too():
    # §556b: rent falls due at the start of the month, so the month counts.
    assert months_running(date(2025, 9, 1), date(2026, 9, 1)) == 13


# ── how long somebody has stayed is time passed, not time agreed ──────────

def test_a_sitting_tenant_has_stayed_as_long_as_they_have_been_there():
    # A twelve-month term signed two months ago is two months stayed. Reading
    # the contracted end instead would credit a tenant who has just moved in
    # with the whole year.
    rows = build([tenancy(1, "A", "2026-10-01", "2027-09-30")], TODAY)["tenancies"]
    assert rows[0]["status"] == CURRENT
    assert rows[0]["months"] == 2          # October and November


def test_a_rent_step_dated_ahead_is_not_reported_as_the_rent_now():
    # §557a agrees the steps years in advance; the current rent is the one in
    # force today, not the last one on the schedule.
    rows = build([tenancy(1, "A", "2026-01-01", "2028-12-31",
                          rents=(("2026-01-01", 500, 100),
                                 ("2028-01-01", 600, 100)))], TODAY)["tenancies"]
    assert rows[0]["rent_end"] == 500.0
    assert rows[0]["rent_changes"] == 1    # the step is on file, just not owed


def test_a_term_ending_next_spring_is_a_handover_not_a_vacancy():
    # Gaps are measured on the terms as contracted: the current tenancy runs
    # to March and the next begins in April, so nothing stands empty.
    history = build([
        tenancy(1, "Sitting", "2026-01-01", "2027-03-31"),
        tenancy(2, "Next", "2027-04-01", None),
    ], TODAY)
    rows = {r["tenant_name"]: r for r in history["tenancies"]}
    assert rows["Next"]["gap_days_before"] == 0
    assert history["summary"]["occupancy_pct"] == 100.0


# ── gaps between tenancies ────────────────────────────────────────────────

def test_the_gap_before_each_tenancy_is_measured_against_the_one_before_it():
    history = build([
        tenancy(1, "First", "2024-01-01", "2024-06-30"),
        tenancy(2, "Second", "2024-09-01", "2025-03-31"),
    ], TODAY)
    rows = {r["tenant_name"]: r for r in history["tenancies"]}
    assert rows["First"]["gap_days_before"] is None      # nothing came before
    assert rows["Second"]["gap_days_before"] == 62       # July and August


def test_a_tenant_moving_in_the_day_after_the_last_one_left_is_no_gap():
    back_to_back = [tenancy(1, "First", "2024-01-01", "2024-06-30"),
                    tenancy(2, "Second", "2024-07-01", "2024-12-31")]
    rows = {r["tenant_name"]: r
            for r in build(back_to_back, TODAY)["tenancies"]}
    assert rows["Second"]["gap_days_before"] == 0
    # The two terms are one unbroken stretch of letting, so the only gap the
    # unit has is the one still running since the second tenant left.
    assert (summary_of(*back_to_back)["longest_gap_days"]
            == (TODAY - date(2024, 12, 31)).days)


# ── occupancy ─────────────────────────────────────────────────────────────

def test_a_unit_let_without_a_break_is_fully_occupied():
    s = summary_of(tenancy(1, "A", "2024-01-01", None))
    assert s["occupancy_pct"] == 100.0
    assert s["vacant_days"] == 0
    assert s["vacant_since"] is None


def test_the_empty_months_come_off_the_occupancy():
    # Let 1 Jan–30 Jun 2026, empty since: 181 days let out of the span.
    s = summary_of(tenancy(1, "A", "2026-01-01", "2026-06-30"))
    span = (TODAY - date(2026, 1, 1)).days + 1
    assert s["let_days"] == 181
    assert s["span_days"] == span
    assert s["vacant_days"] == span - 181
    assert s["occupancy_pct"] == round(100.0 * 181 / span, 1)


def test_a_stretch_still_empty_is_the_longest_gap_and_dated():
    # The gap that matters is after the last tenant, not between two of them.
    s = summary_of(tenancy(1, "A", "2025-01-01", "2025-04-30"))
    assert s["vacant_since"] == "2025-05-01"
    assert s["longest_gap_days"] == (TODAY - date(2025, 4, 30)).days
    assert s["longest_gap_days"] > 0


def test_a_tenancy_that_has_not_begun_is_not_counted_as_time_let():
    # A term starting next year must not make the room look occupied now.
    s = summary_of(tenancy(1, "A", "2027-02-01", None))
    assert s["upcoming"] == 1
    assert s["occupancy_pct"] is None
    assert s["let_days"] is None


def test_a_future_term_does_not_lift_the_occupancy_of_a_let_unit():
    s = summary_of(
        tenancy(1, "A", "2026-01-01", "2026-06-30"),
        tenancy(2, "B", "2027-01-01", None),
    )
    only_past = summary_of(tenancy(1, "A", "2026-01-01", "2026-06-30"))
    assert s["occupancy_pct"] == only_past["occupancy_pct"]
    assert s["upcoming"] == 1


def test_two_contracts_over_the_same_weeks_cannot_push_occupancy_past_full():
    # Overlapping terms on one unit are a data error, not 200 % occupancy.
    s = summary_of(
        tenancy(1, "A", "2026-01-01", "2026-06-30"),
        tenancy(2, "B", "2026-03-01", "2026-06-30"),
    )
    assert s["occupancy_pct"] <= 100.0
    assert s["let_days"] == 181


# ── how long tenants stay ─────────────────────────────────────────────────

def test_the_average_tenancy_counts_only_the_ones_that_ended():
    # A running tenancy is still getting longer; averaging it in would make
    # turnover look faster than it is.
    s = summary_of(
        tenancy(1, "A", "2023-01-01", "2023-12-31"),   # 12 months
        tenancy(2, "B", "2024-01-01", "2024-06-30"),   # 6 months
        tenancy(3, "C", "2024-07-01", None),           # still running
    )
    assert s["completed"] == 2
    assert s["avg_tenancy_months"] == 9.0


def test_a_unit_with_only_a_sitting_tenant_has_no_average_to_report():
    assert summary_of(tenancy(1, "A", "2024-01-01", None))["avg_tenancy_months"] is None


# ── rent across the handovers ─────────────────────────────────────────────

def test_the_rent_progression_runs_from_the_first_tenancy_to_the_current_one():
    s = summary_of(
        tenancy(1, "A", "2023-01-01", "2023-12-31", rents=(("2023-01-01", 450, 90),)),
        tenancy(2, "B", "2024-01-01", None,
                rents=(("2024-01-01", 500, 100), ("2025-07-01", 560, 110))),
    )
    assert s["rent_first"] == 450.0
    assert s["rent_now"] == 560.0


def test_a_tenancy_reports_the_rent_it_started_and_ended_at():
    rows = build([tenancy(1, "A", "2024-01-01", "2025-12-31",
                          rents=(("2024-01-01", 500, 100),
                                 ("2025-01-01", 540, 110)))], TODAY)["tenancies"]
    assert rows[0]["rent_start"] == 500.0
    assert rows[0]["nkv_start"] == 100.0
    assert rows[0]["rent_end"] == 540.0
    assert rows[0]["rent_changes"] == 1


def test_a_tenancy_with_no_rent_on_file_says_so_rather_than_reporting_zero():
    rows = build([tenancy(1, "A", "2024-01-01", None, rents=())], TODAY)["tenancies"]
    assert rows[0]["rent_start"] is None
    assert rows[0]["rent_end"] is None


# ── order, and the rows that cannot be placed ─────────────────────────────

def test_the_current_tenant_is_first_in_the_list():
    rows = build([
        tenancy(1, "Older", "2023-01-01", "2023-12-31"),
        tenancy(2, "Current", "2024-01-01", None),
    ], TODAY)["tenancies"]
    assert [r["tenant_name"] for r in rows] == ["Current", "Older"]


def test_a_tenancy_with_an_unusable_start_date_is_listed_but_not_placed():
    # 'None' is what the TEXT date columns held before the backfill, and a
    # string that sorts after a real date would scramble the whole timeline.
    rows = build([
        tenancy(1, "Dated", "2024-01-01", None),
        tenancy(2, "Undated", "None", None),
    ], TODAY)["tenancies"]
    assert [r["tenant_name"] for r in rows] == ["Dated", "Undated"]
    undated = rows[-1]
    assert undated["start_date"] is None
    assert undated["gap_days_before"] is None
    assert undated["months"] is None
    s = summary_of(tenancy(1, "Dated", "2024-01-01", None),
                   tenancy(2, "Undated", "None", None))
    assert s["tenancies"] == 2 and s["undated"] == 1
    assert s["occupancy_pct"] == 100.0        # measured on what can be placed


def test_a_tenancy_marked_over_without_an_end_date_admits_the_date_is_missing():
    rows = build([tenancy(1, "A", "2024-01-01", None, terminated=1)], TODAY)["tenancies"]
    assert rows[0]["status"] == PAST
    assert rows[0]["end_known"] is False
    assert rows[0]["end_date"] is None


def test_an_empty_unit_reports_nothing_rather_than_dividing_by_zero():
    s = summary_of()
    assert s["tenancies"] == 0
    assert s["occupancy_pct"] is None
    assert s["longest_gap_days"] is None


# ── the deposit keeps its own currency ────────────────────────────────────

def test_a_deposit_agreed_in_another_tender_keeps_its_currency():
    rows = build([tenancy(1, "A", "2024-01-01", None,
                          kaution_amount=8000, kaution_currency="cny")],
                 TODAY)["tenancies"]
    assert rows[0]["kaution_amount"] == 8000.0
    assert rows[0]["kaution_currency"] == "CNY"


def test_a_deposit_with_no_currency_on_file_is_euros():
    rows = build([tenancy(1, "A", "2024-01-01", None, kaution_amount=1500)],
                 TODAY)["tenancies"]
    assert rows[0]["kaution_currency"] == "EUR"
