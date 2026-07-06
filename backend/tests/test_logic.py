"""Unit tests for the Nebenkostenabrechnung cost calculations in logic.py.

These functions are pure arithmetic (day-based proration across tenants), so we
pin down their behaviour with round-number inputs whose expected results are
easy to verify by hand. `eff_days == bill_days == 365` and `num_tenants == 1`
makes the proration factor 1.0, isolating the cost math.
"""
from datetime import date

import pytest

import logic


# ── Detailed, meter-based calculations ────────────────────────────────────────

def test_strom_calc_detail_full_year_single_tenant():
    r = logic.strom_calc_detail(
        start_kwh=1000, end_kwh=1300, arbeitspreis=0.30,
        grundpreis_monthly=10, num_tenants=1, bill_days=365,
        eff_days=365, prepay_monthly=15,
    )
    assert r["verbrauch"] == 300.0
    assert r["verbrauch_tenant"] == pytest.approx(300.0)
    assert r["arbeitskosten"] == pytest.approx(90.0)   # 300 kWh × 0.30
    assert r["grundkosten"] == pytest.approx(120.0)    # 10 €/mo × 12
    assert r["cost_tenant"] == pytest.approx(210.0)
    assert r["prepay"] == pytest.approx(180.0)         # 15 €/mo × 12
    assert r["nach"] == pytest.approx(30.0)


def test_strom_calc_detail_splits_across_tenants():
    one = logic.strom_calc_detail(1000, 1300, 0.30, 10, 1, 365, 365, 0)
    two = logic.strom_calc_detail(1000, 1300, 0.30, 10, 2, 365, 365, 0)
    assert two["cost_tenant"] == pytest.approx(one["cost_tenant"] / 2)


def test_strom_calc_detail_negative_consumption_clamped():
    r = logic.strom_calc_detail(1300, 1000, 0.30, 0, 1, 365, 365, 0)
    assert r["verbrauch"] == 0.0
    assert r["arbeitskosten"] == 0.0


def test_gas_calc_detail_applies_conversion_factor():
    r = logic.gas_calc_detail(
        start_m3=0, end_m3=100, umrechnungsfaktor=10, arbeitspreis=0.05,
        grundpreis_monthly=0, num_tenants=1, bill_days=365, eff_days=365,
        prepay_monthly=0,
    )
    assert r["verbrauch_m3"] == 100.0
    assert r["verbrauch_kwh"] == pytest.approx(1000.0)   # 100 m³ × 10 kWh/m³
    assert r["arbeitskosten"] == pytest.approx(50.0)     # 1000 kWh × 0.05
    assert r["nach"] == pytest.approx(50.0)


def test_water_calc_detail_sums_fresh_and_waste():
    r = logic.water_calc_detail(
        start_m3=100, end_m3=200, frischwasser_per_m3=2.0,
        abwasser_per_m3=3.0, num_tenants=1, bill_days=365, eff_days=365,
        prepay_monthly=0,
    )
    assert r["cost_per_m3"] == pytest.approx(5.0)
    assert r["cost_flat"] == pytest.approx(500.0)        # 100 m³ × 5
    assert r["cost_tenant"] == pytest.approx(500.0)
    assert r["nach"] == pytest.approx(500.0)


def test_warmwasser_calc_detail_totals_all_meters():
    r = logic.warmwasser_calc_detail(
        meters=[{"start": 0, "end": 10}, {"start": 0, "end": 5}],
        frischwasser_per_m3=2.0, abwasser_per_m3=3.0, heizenergie_per_m3=5.0,
        num_tenants=1, bill_days=365, eff_days=365, prepay_monthly=0,
    )
    assert r["verbrauch_m3"] == pytest.approx(15.0)      # 10 + 5
    assert r["cost_per_m3"] == pytest.approx(10.0)       # 2 + 3 + 5
    assert r["cost_flat"] == pytest.approx(150.0)
    assert len(r["meter_details"]) == 2


def test_heizung_calc_detail_costs_per_meter():
    r = logic.heizung_calc_detail(
        meters=[{"start": 0, "end": 100, "conversion_factor": 1.0,
                 "unit_price": 0.10}],
        num_tenants=1, bill_days=365, eff_days=365, prepay_monthly=0,
    )
    assert r["total_units"] == pytest.approx(100.0)
    assert r["total_cost_flat"] == pytest.approx(10.0)   # 100 kWh × 0.10
    assert r["cost_tenant"] == pytest.approx(10.0)


# ── Direct total-cost calculation ─────────────────────────────────────────────

def test_sum_cost_calc_settles_to_zero():
    r = logic.sum_cost_calc(
        cost_flat=1200, num_tenants=1, bill_days=365, eff_days=365,
        prepay_monthly=100,
    )
    assert r["cost_tenant"] == pytest.approx(1200.0)
    assert r["prepay"] == pytest.approx(1200.0)          # 100 €/mo × 12
    assert r["nach"] == pytest.approx(0.0)


def test_sum_cost_calc_pauschale_never_negative():
    over = logic.sum_cost_calc(100, 1, 365, 365, 200, is_pauschale=True)
    assert over["nach"] == 0.0
    plain = logic.sum_cost_calc(100, 1, 365, 365, 200, is_pauschale=False)
    assert plain["nach"] < 0


def test_sum_cost_calc_zero_tenants_does_not_divide_by_zero():
    # num_tenants is clamped to at least 1 internally.
    r = logic.sum_cost_calc(1200, 0, 365, 365, 0)
    assert r["cost_tenant"] == pytest.approx(1200.0)


# ── Legacy tuple-returning helpers ────────────────────────────────────────────

def test_strom_calc_legacy_tuple():
    cost_per_tenant, limit_period, nachzahlung = logic.strom_calc(
        cost_flat=365, tenants=1, bill_days=365, eff_days=365,
        limit_per_month=50,
    )
    assert cost_per_tenant == pytest.approx(365.0)
    assert limit_period == pytest.approx(600.0)          # 50 × 12
    assert nachzahlung == pytest.approx(-235.0)


def test_betriebskosten_calc_full_year():
    cost_per_tenant, period_cost, limit_period, nachzahlung = \
        logic.betriebskosten_calc(
            cost_flat=1200, tenants=1, months=12,
            bk_start=date(2024, 1, 1), bk_end=date(2024, 12, 1),
            limit_per_month=206,
        )
    assert cost_per_tenant == pytest.approx(1200.0)
    assert period_cost == pytest.approx(1200.0)
    assert limit_period == pytest.approx(2472.0)         # 206 × 12
    assert nachzahlung == pytest.approx(-1272.0)


def test_betriebskosten_calc_partial_period_prorates():
    # 6 of 12 months billed → half the annual per-tenant cost.
    _, period_cost, _, _ = logic.betriebskosten_calc(
        cost_flat=1200, tenants=1, months=6,
        bk_start=date(2024, 1, 1), bk_end=date(2024, 12, 1),
    )
    assert period_cost == pytest.approx(600.0)
