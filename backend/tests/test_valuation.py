"""What a flat is worth, and how much of that is the ground under it.

The rule that matters most here: an estimate is never presented as a valuation.
A district's average €/m² is not this flat's worth, and anything not priced by
the owner comes back flagged so the UI can say so.
"""
import pytest

from valuation import (land_per_floor_sqm, land_share, portfolio_totals,
                       value_property)


# ── Land value per m² of floor space ─────────────────────────────────────────

def test_the_gfz_turns_a_land_price_into_a_floor_price():
    """A m² of land carrying 2,5 m² of floor space spreads its 4.000 € over
    that floor space."""
    assert land_per_floor_sqm(4000, 2.5) == 1600.0


def test_without_a_gfz_there_is_no_conversion():
    assert land_per_floor_sqm(4000, None) is None
    assert land_per_floor_sqm(4000, 0) is None
    assert land_per_floor_sqm(None, 2.5) is None


# ── The flat's share of the land ─────────────────────────────────────────────

def test_the_land_share_is_brw_times_plot_times_mea():
    # 2.800 €/m² × 500 m² plot × 87/1000 = 121.800 €
    assert land_share(2800, 500, 87) == pytest.approx(121_800.0)


def test_an_mea_already_given_as_a_share_is_taken_as_one():
    assert land_share(2800, 500, 0.087) == pytest.approx(121_800.0)


@pytest.mark.parametrize("mea", [0, None, 1001, -5])
def test_an_unusable_mea_yields_no_share(mea):
    assert land_share(2800, 500, mea) is None


def test_without_a_plot_area_there_is_no_exact_share():
    """The GFZ approximation is reported instead; this one needs the real plot."""
    assert land_share(2800, None, 87) is None


# ── The property's value ─────────────────────────────────────────────────────

def test_a_comparable_values_the_flat_by_its_living_area():
    v = value_property(living_sqm=49.0, comparable_per_sqm=5400,
                       brw=2800, gfz=2.5, stichtag="2026-01-01")
    assert v["estimate"] == pytest.approx(264_600.0)
    assert v["value"] == pytest.approx(264_600.0)
    assert v["basis"] == "comparable"
    assert v["estimated"] is True
    assert v["value_date"] == "2026-01-01"


def test_the_owners_own_figure_wins_over_the_district_average():
    """An appraisal is a fact about this flat; a comparable is an average over
    a district. Both are returned so a stale appraisal is visible."""
    v = value_property(living_sqm=49.0, comparable_per_sqm=5400,
                       market_value=280_000, market_value_date="2026-06-01",
                       brw=2800, gfz=2.5, stichtag="2026-01-01")
    assert v["value"] == 280_000.0
    assert v["basis"] == "own"
    assert v["estimated"] is False
    assert v["value_date"] == "2026-06-01"
    assert v["estimate"] == pytest.approx(264_600.0)      # still shown alongside


def test_a_flat_with_no_area_cannot_be_valued_and_says_what_is_missing():
    """Two WG properties here have no size on any room, so the flat's area is
    unknown — the page has to ask for it rather than invent a number."""
    v = value_property(comparable_per_sqm=5400, brw=4000, gfz=2.5)
    assert v["value"] is None
    assert v["basis"] is None
    assert v["missing"] == ["living_sqm"]


def test_a_flat_with_no_comparable_says_that_too():
    v = value_property(living_sqm=49.0, brw=2800, gfz=2.5)
    assert v["value"] is None
    assert v["missing"] == ["comparable_per_sqm"]


def test_an_own_figure_needs_nothing_else():
    v = value_property(market_value=280_000, market_value_date="2026-06-01")
    assert v["value"] == 280_000.0
    assert v["missing"] == []


def test_the_land_percentage_uses_the_exact_share_when_the_plot_is_known():
    v = value_property(living_sqm=49.0, comparable_per_sqm=5400,
                       brw=2800, gfz=2.5, plot_sqm=500, mea=87)
    assert v["land_share"] == pytest.approx(121_800.0)
    assert v["land_pct"] == pytest.approx(121_800 / 264_600 * 100, abs=0.1)


def test_the_land_percentage_falls_back_to_the_gfz_approximation():
    """Without a plot area, BRW ÷ GFZ × living area still says roughly how much
    of the price is location rather than building."""
    v = value_property(living_sqm=49.0, comparable_per_sqm=5400, brw=2800, gfz=2.5)
    assert v["land_share"] is None
    assert v["land_pct"] == pytest.approx(1120 * 49 / 264_600 * 100, abs=0.1)


def test_the_value_per_sqm_comes_back_for_comparison():
    v = value_property(living_sqm=50.0, market_value=300_000)
    assert v["per_sqm"] == 6000.0


# ── Portfolio totals ─────────────────────────────────────────────────────────

def test_totals_are_value_debt_and_equity():
    vals = [{"value": 300_000.0, "estimated": False},
            {"value": 200_000.0, "estimated": False}]
    t = portfolio_totals(vals, [150_000, 50_000])
    assert t["value"] == 500_000.0
    assert t["debt"] == 200_000.0
    assert t["equity"] == 300_000.0
    assert t["ltv"] == 40.0
    assert t["estimated"] is False


def test_totals_are_withheld_while_any_property_has_no_value():
    """A total that silently leaves out the unvalued flats reads as the whole
    portfolio and understates it."""
    vals = [{"value": 300_000.0, "estimated": False}, {"value": None, "estimated": True}]
    assert portfolio_totals(vals, [150_000, 0]) is None


def test_totals_say_when_any_figure_is_an_estimate():
    vals = [{"value": 300_000.0, "estimated": False},
            {"value": 200_000.0, "estimated": True}]
    assert portfolio_totals(vals, [0, 0])["estimated"] is True


def test_an_empty_portfolio_has_no_totals():
    assert portfolio_totals([], []) is None


def test_debt_above_value_gives_negative_equity_not_an_error():
    """Possible early in a loan, and the figure is the point."""
    t = portfolio_totals([{"value": 100_000.0, "estimated": False}], [130_000])
    assert t["equity"] == -30_000.0
    assert t["ltv"] == 130.0
