"""A tenancy whose rent changes, and the months on either side of the change.

The bug this replaces: one `contracts.rent` used for every month, so a §558
increase restated what was expected in months that had already been filed —
all twelve of a closed year, with the arrears history and every Mahnung built
on it.
"""
from decimal import Decimal

import pytest

from rent_periods import (
    KIND_LABELS, KINDS, RentSchedule, cold_rent, kaution_cap, rent_at,
    schedules_from_rows,
)


@pytest.fixture
def raised():
    """1.050 € from the start of the tenancy, 1.150 € from July 2026."""
    return RentSchedule([
        ("2024-05-01", Decimal("1050.00"), Decimal("230.00")),
        ("2026-07-01", Decimal("1150.00"), Decimal("260.00")),
    ])


# ── which price a day falls under ────────────────────────────────────────────

def test_the_month_before_the_increase_is_the_old_price(raised):
    assert raised.on("2026-06-01") == Decimal("1050.00")
    assert raised.on("2026-06-30") == Decimal("1050.00")


def test_the_month_it_starts_is_the_new_price(raised):
    assert raised.on("2026-07-01") == Decimal("1150.00")
    assert raised.on("2030-01-01") == Decimal("1150.00")


def test_before_the_tenancy_there_is_no_rent(raised):
    # Not an error and not the first price: a contract that has not started
    # owes nothing, and the balance sheet must not expect a payment.
    assert raised.on("2024-04-30") == Decimal("0")


def test_the_prepayment_travels_with_the_price(raised):
    assert raised.nkv_on("2026-06-01") == Decimal("230.00")
    assert raised.nkv_on("2026-07-01") == Decimal("260.00")
    assert raised.nkv_on("2024-01-01") is None


def test_periods_sort_themselves():
    s = RentSchedule([("2026-07-01", 1150), ("2024-05-01", 1050)])
    assert s.on("2025-01-01") == Decimal("1050")
    assert s.on("2026-12-01") == Decimal("1150")


def test_a_period_with_no_start_has_always_applied():
    # Legacy rows: a contract whose rent was never dated.
    s = RentSchedule([(None, 900), ("2026-01-01", 950)])
    assert s.on("1999-01-01") == Decimal("900")
    assert s.on("2026-06-01") == Decimal("950")


def test_the_string_none_counts_as_blank():
    assert RentSchedule([("None", 900)]).on("2020-01-01") == Decimal("900")


# ── a Staffelmiete is just several periods ───────────────────────────────────

def test_a_staffel_is_a_schedule_of_its_own():
    # §557a: the steps are agreed once, at signing, and each is owed from its
    # own date. Entering them up front is the whole point.
    staffel = RentSchedule([("2025-01-01", 900), ("2026-01-01", 930),
                            ("2027-01-01", 960), ("2028-01-01", 990)])
    assert staffel.on("2025-12-31") == Decimal("900")
    assert staffel.on("2026-01-01") == Decimal("930")
    assert staffel.on("2028-06-01") == Decimal("990")


def test_steps_still_to_come_can_be_listed():
    staffel = RentSchedule([("2025-01-01", 900), ("2026-01-01", 930),
                            ("2027-01-01", 960)])
    upcoming = staffel.changes_after("2026-05-01")
    assert [p[0] for p in upcoming] == ["2027-01-01"]
    assert staffel.changes_after("2030-01-01") == []


def test_every_kind_has_a_label_naming_its_paragraph():
    assert set(KIND_LABELS) == set(KINDS)
    assert "§557a" in KIND_LABELS["staffel"]
    assert "§558" in KIND_LABELS["agreed"]


# ── the resolver the readers share ───────────────────────────────────────────

def test_a_schedule_resolves_per_date(raised):
    assert rent_at(raised, "2026-06-01") == Decimal("1050.00")
    assert rent_at(raised, "2026-07-01") == Decimal("1150.00")


def test_a_plain_amount_still_works():
    # The readers are shared with callers that hold a single figure; passing
    # one must not raise, it simply means "the same in every month".
    assert rent_at(1050, "2026-06-01") == Decimal("1050")
    assert rent_at(Decimal("1050.50"), "2099-01-01") == Decimal("1050.50")
    assert rent_at(None, "2026-01-01") == Decimal("0")


def test_rows_group_into_one_schedule_per_contract():
    rows = [
        (7, "2024-05-01", Decimal("1050"), Decimal("230")),
        (7, "2026-07-01", Decimal("1150"), Decimal("260")),
        (9, "2023-01-01", Decimal("620"), None),
    ]
    schedules = schedules_from_rows(rows)
    assert set(schedules) == {7, 9}
    assert schedules[7].on("2026-08-01") == Decimal("1150")
    assert schedules[9].on("2026-08-01") == Decimal("620")
    assert len(schedules[7]) == 2


def test_an_empty_schedule_is_falsy_and_costs_nothing():
    s = RentSchedule([])
    assert not s
    assert s.on("2026-01-01") == Decimal("0")
    assert s.first() == Decimal("0")


# ── §551: what a deposit may be ──────────────────────────────────────────────

def test_the_deposit_cap_is_three_cold_rents():
    assert kaution_cap(Decimal("820.00")) == Decimal("2460.00")


def test_the_cap_is_computed_on_the_cold_rent_not_the_warm_one():
    # Three *Kaltmieten*. Using the warm rent would quietly allow a deposit a
    # fifth too large, which the tenant can reclaim at any time.
    warm, nkv = Decimal("1050.00"), Decimal("230.00")
    assert cold_rent(warm, nkv) == Decimal("820.00")
    assert kaution_cap(cold_rent(warm, nkv)) == Decimal("2460.00")
    assert kaution_cap(warm) == Decimal("3150.00")


def test_a_missing_prepayment_means_the_whole_rent_is_cold():
    assert cold_rent(Decimal("820"), None) == Decimal("820")


# ── a tax year in which the rent was raised ──────────────────────────────────

def test_a_year_is_summed_at_the_price_each_month_began_at():
    # 1.050 € to June, 1.150 € from July: the Anlage V figure is what was
    # owed, not twelve times whichever price the contract carries today.
    s = RentSchedule([("2024-05-01", 1050), ("2026-07-01", 1150)])
    from rent_periods import year_total
    months, total = year_total(s, "2024-05-01", None, 2026)
    assert months == 12
    assert total == Decimal("1050") * 6 + Decimal("1150") * 6
    assert total == Decimal("13200")


def test_a_tenancy_that_starts_mid_year_counts_from_its_month():
    from rent_periods import months_in_year, year_total
    assert len(months_in_year("2026-05-20", None, 2026)) == 8
    months, total = year_total(RentSchedule([("2026-05-20", 900)]),
                               "2026-05-20", None, 2026)
    assert (months, total) == (8, Decimal("7200"))


def test_a_tenancy_that_ended_stops_counting():
    from rent_periods import months_in_year
    assert len(months_in_year("2020-01-01", "2026-03-31", 2026)) == 3
    assert months_in_year("2020-01-01", "2025-12-31", 2026) == []


def test_a_year_before_the_tenancy_is_no_months_and_no_rent():
    from rent_periods import year_total
    assert year_total(RentSchedule([("2026-01-01", 900)]), "2026-01-01", None, 2025) \
        == (0, Decimal("0"))


def test_a_month_the_tenancy_started_in_is_priced_at_its_first_rent():
    # A tenancy beginning on the 20th has its first period dated that day.
    # Asking for the first of the month would answer "nothing agreed yet" and
    # lose the month, so the month rule answers with the price it started at.
    s = RentSchedule([("2026-05-20", 900)])
    assert s.on("2026-05-01") == Decimal("0")          # strictly, that day
    assert s.for_month("2026-05-01") == Decimal("900")  # the month it ran in
    assert s.for_month("2026-06-01") == Decimal("900")


def test_the_month_rule_still_prefers_a_price_that_had_started():
    s = RentSchedule([("2024-05-01", 1050), ("2026-07-01", 1150)])
    assert s.for_month("2026-06-01") == Decimal("1050")
    assert s.for_month("2026-07-01") == Decimal("1150")


def test_the_month_rule_accepts_a_plain_amount_too():
    from rent_periods import rent_for_month
    assert rent_for_month(900, "2026-05-01") == Decimal("900")
    assert rent_for_month(RentSchedule([("2026-05-20", 900)]), "2026-05-01") == Decimal("900")


# ── §558: what an ordinary increase has to satisfy ───────────────────────────

def _codes(findings):
    return {f["code"] for f in findings}


def test_a_modest_increase_after_three_years_passes_quietly():
    from rent_periods import check_increase
    s = RentSchedule([("2021-01-01", 1000), ("2023-01-01", 1050)])
    assert check_increase(s, "2026-07-01", 1150) == []


def test_an_increase_over_the_tight_cap_names_both_thresholds():
    from rent_periods import check_increase
    s = RentSchedule([("2023-01-01", 1000)])
    f = check_increase(s, "2026-07-01", 1180)          # +18 %
    assert "kappungsgrenze" in _codes(f)
    hit = [x for x in f if x["code"] == "kappungsgrenze"][0]
    assert hit["over_general"] is False
    assert "15 %" in hit["message"] and "20 %" in hit["message"]
    assert hit["paragraph"] == "§558 Abs. 3 BGB"


def test_an_increase_over_the_general_cap_says_so():
    from rent_periods import check_increase
    s = RentSchedule([("2023-01-01", 1000)])
    hit = [x for x in check_increase(s, "2026-07-01", 1250)
           if x["code"] == "kappungsgrenze"][0]
    assert hit["over_general"] is True


def test_the_cap_is_measured_against_three_years_ago_not_the_current_rent():
    from rent_periods import check_increase
    # Raised in steps: 1000 → 1100 → 1150. Against the current 1150 the last
    # step is 4 %; against the 1000 of three years ago it is 15 % — which is
    # the comparison §558 Abs. 3 actually makes.
    s = RentSchedule([("2023-06-01", 1000), ("2025-01-01", 1100)])
    f = check_increase(s, "2026-07-01", 1210)
    assert "kappungsgrenze" in _codes(f)


def test_an_increase_too_soon_after_the_last_one_is_flagged():
    from rent_periods import check_increase
    s = RentSchedule([("2020-01-01", 900), ("2026-01-01", 1000)])
    f = check_increase(s, "2026-09-01", 1030)          # eight months later
    hit = [x for x in f if x["code"] == "wartefrist"][0]
    assert "15" in hit["message"]
    assert hit["paragraph"] == "§558 Abs. 1 BGB"


def test_the_waiting_period_does_not_apply_to_the_first_increase():
    from rent_periods import check_increase
    s = RentSchedule([("2026-01-01", 1000)])
    assert "wartefrist" not in _codes(check_increase(s, "2026-09-01", 1030))


def test_the_other_kinds_answer_to_their_own_paragraphs():
    from rent_periods import check_increase
    s = RentSchedule([("2026-01-01", 1000)])
    for kind in ("staffel", "index", "modernisation", "initial"):
        assert check_increase(s, "2026-07-01", 1400, kind=kind) == []


def test_a_reduction_is_recorded_but_remarked_on():
    from rent_periods import check_increase
    s = RentSchedule([("2024-01-01", 1000)])
    f = check_increase(s, "2026-07-01", 900)
    assert "reduction" in _codes(f)


def test_nothing_is_claimed_about_a_tenancy_with_no_prices():
    from rent_periods import check_increase
    assert check_increase(RentSchedule([]), "2026-07-01", 1200) == []
