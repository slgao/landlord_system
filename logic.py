#! /usr/bin/env python
# coding=utf-8
# ================================================================
#   Copyright (C) 2026 * Ltd. All rights reserved.
#
#   Editor      : EMACS
#   File name   : logic.py
#   Author      : slgao
#   Created date: Sun Mar 08 2026 18:21:07
#   Description :
#
# ================================================================
import calendar as _calendar
from datetime import date as _date
from db import fetch


def strom_calc(cost_flat, tenants, bill_days, eff_days, limit_per_month=50):
    """
    cost_flat    – total electricity cost for the whole flat over the billing period
    bill_days    – length of the provider's billing period in days
    eff_days     – days the tenant actually lived in the flat (effective period)
    """
    cost_per_day_flat = cost_flat / bill_days
    cost_per_tenant   = cost_per_day_flat * eff_days / tenants
    limit_day         = (limit_per_month * 12) / 365 / tenants
    limit_period      = limit_day * eff_days
    nachzahlung       = cost_per_tenant - limit_period
    return cost_per_tenant, limit_period, nachzahlung


def gas_calc(cost_flat, tenants, bill_days, eff_days, limit_per_month=0):
    """
    cost_flat    – total gas cost for the whole flat over the billing period
    bill_days    – length of the provider's billing period in days
    eff_days     – days the tenant actually lived in the flat (effective period)
    """
    cost_per_day_flat = cost_flat / bill_days
    cost_per_tenant   = cost_per_day_flat * eff_days / tenants
    limit_day         = (limit_per_month * 12) / 365 / tenants
    limit_period      = limit_day * eff_days
    nachzahlung       = cost_per_tenant - limit_period
    return cost_per_tenant, limit_period, nachzahlung


def water_calc(cost_flat, tenants, bill_days, eff_days, limit_per_month=0):
    """
    cost_flat    – total cold water cost for the whole flat over the billing period
    bill_days    – length of the provider's billing period in days
    eff_days     – days the tenant actually lived in the flat (effective period)
    """
    cost_per_day_flat = cost_flat / bill_days
    cost_per_tenant   = cost_per_day_flat * eff_days / tenants
    limit_day         = (limit_per_month * 12) / 365 / tenants
    limit_period      = limit_day * eff_days
    nachzahlung       = cost_per_tenant - limit_period
    return cost_per_tenant, limit_period, nachzahlung


def strom_calc_detail(start_kwh, end_kwh, arbeitspreis, grundpreis_monthly,
                      num_tenants, bill_days, eff_days, prepay_monthly,
                      is_pauschale=False):
    """
    Detailed Strom calculation from meter readings.
    Grundpreis is per month; prorated daily to tenant's effective period.
    """
    n  = max(1, num_tenants)
    bd = max(1, bill_days)
    verbrauch          = max(0.0, end_kwh - start_kwh)
    verbrauch_tenant   = verbrauch * eff_days / bd / n
    arbeitskosten      = verbrauch_tenant * arbeitspreis
    grundkosten        = grundpreis_monthly * 12 / 365 * eff_days / n
    cost_tenant        = arbeitskosten + grundkosten
    prepay             = prepay_monthly * 12 / 365 * eff_days
    nach               = cost_tenant - prepay
    if is_pauschale:
        nach = max(0.0, nach)
    return dict(
        verbrauch           = round(verbrauch, 2),
        verbrauch_tenant    = round(verbrauch_tenant, 3),
        arbeitskosten       = round(arbeitskosten, 2),
        grundkosten         = round(grundkosten, 2),
        cost_tenant         = round(cost_tenant, 2),
        prepay              = round(prepay, 2),
        nach                = round(nach, 2),
    )


def gas_calc_detail(start_m3, end_m3, umrechnungsfaktor, arbeitspreis, grundpreis_monthly,
                    num_tenants, bill_days, eff_days, prepay_monthly,
                    is_pauschale=False):
    """
    Detailed Gas calculation from meter readings.
    umrechnungsfaktor: kWh/m³ (Brennwert × Zustandszahl, from the gas bill).
    Grundpreis prorated daily.
    """
    n  = max(1, num_tenants)
    bd = max(1, bill_days)
    verbrauch_m3       = max(0.0, end_m3 - start_m3)
    verbrauch_kwh      = verbrauch_m3 * umrechnungsfaktor
    verbrauch_kwh_t    = verbrauch_kwh * eff_days / bd / n
    arbeitskosten      = verbrauch_kwh_t * arbeitspreis
    grundkosten        = grundpreis_monthly * 12 / 365 * eff_days / n
    cost_tenant        = arbeitskosten + grundkosten
    prepay             = prepay_monthly * 12 / 365 * eff_days
    nach               = cost_tenant - prepay
    if is_pauschale:
        nach = max(0.0, nach)
    return dict(
        verbrauch_m3        = round(verbrauch_m3, 3),
        verbrauch_kwh       = round(verbrauch_kwh, 2),
        verbrauch_kwh_t     = round(verbrauch_kwh_t, 3),
        arbeitskosten       = round(arbeitskosten, 2),
        grundkosten         = round(grundkosten, 2),
        cost_tenant         = round(cost_tenant, 2),
        prepay              = round(prepay, 2),
        nach                = round(nach, 2),
    )


def water_calc_detail(start_m3, end_m3, frischwasser_per_m3, abwasser_per_m3,
                      num_tenants, bill_days, eff_days, prepay_monthly,
                      is_pauschale=False):
    """
    Detailed cold-water calculation from meter readings.
    No Grundpreis — water is billed purely by consumption.
    """
    n  = max(1, num_tenants)
    bd = max(1, bill_days)
    verbrauch_m3   = max(0.0, end_m3 - start_m3)
    cost_per_m3    = frischwasser_per_m3 + abwasser_per_m3
    cost_flat      = verbrauch_m3 * cost_per_m3
    cost_tenant    = cost_flat * eff_days / bd / n
    prepay         = prepay_monthly * 12 / 365 * eff_days
    nach           = cost_tenant - prepay
    if is_pauschale:
        nach = max(0.0, nach)
    return dict(
        verbrauch_m3    = round(verbrauch_m3, 3),
        cost_per_m3     = round(cost_per_m3, 3),
        cost_flat       = round(cost_flat, 2),
        cost_tenant     = round(cost_tenant, 2),
        prepay          = round(prepay, 2),
        nach            = round(nach, 2),
    )


def warmwasser_calc_detail(meters, frischwasser_per_m3, abwasser_per_m3,
                           heizenergie_per_m3, num_tenants, bill_days, eff_days,
                           prepay_monthly, is_pauschale=False):
    """
    Hot-water calculation. Total Verbrauch = sum over all Warmwasserzähler.
    Cost per m³ = Frischwasser + Abwasser + Heizenergie (each landlord-supplied).
    """
    n  = max(1, num_tenants)
    bd = max(1, bill_days)
    meter_details = []
    total_m3 = 0.0
    for m in meters:
        v = max(0.0, m["end"] - m["start"])
        total_m3 += v
        meter_details.append({
            "meter_id":    m.get("meter_id"),
            "serial":      m.get("serial", ""),
            "description": m.get("description", ""),
            "start":       m["start"],
            "end":         m["end"],
            "verbrauch":   round(v, 3),
        })
    cost_per_m3 = frischwasser_per_m3 + abwasser_per_m3 + heizenergie_per_m3
    cost_flat   = total_m3 * cost_per_m3
    cost_tenant = cost_flat * eff_days / bd / n
    prepay      = prepay_monthly * 12 / 365 * eff_days
    nach        = cost_tenant - prepay
    if is_pauschale:
        nach = max(0.0, nach)
    return dict(
        verbrauch_m3    = round(total_m3, 3),
        cost_per_m3     = round(cost_per_m3, 3),
        cost_flat       = round(cost_flat, 2),
        cost_tenant     = round(cost_tenant, 2),
        prepay          = round(prepay, 2),
        nach            = round(nach, 2),
        meter_details   = meter_details,
    )


def heizung_calc_detail(meters, num_tenants, bill_days, eff_days,
                        prepay_monthly, is_pauschale=False):
    """
    meters: list of dicts with keys:
        start, end          – meter readings in native units (e.g. ISTA Einheiten)
        unit_label          – label for native units (e.g. 'Einheiten')
        conversion_factor   – native units → kWh  (from ISTA bill, default 1.0)
        unit_price          – €/kWh  (from ISTA bill)

    Cost per meter = (end − start) × conversion_factor × €/kWh
    """
    n  = max(1, num_tenants)
    bd = max(1, bill_days)
    meter_details = []
    total_cost_flat = 0.0
    total_units = 0.0
    for m in meters:
        raw_units  = max(0.0, m["end"] - m["start"])
        factor     = float(m.get("conversion_factor", 1.0))
        kwh        = raw_units * factor
        cost       = round(kwh * m["unit_price"], 2)
        total_units     += raw_units
        total_cost_flat += cost
        meter_details.append({
            "serial":            m.get("serial", ""),
            "description":       m.get("description", ""),
            "unit_label":        m.get("unit_label", "Einheiten"),
            "start":             m["start"],
            "end":               m["end"],
            "units":             round(raw_units, 3),
            "conversion_factor": round(factor, 4),
            "kwh":               round(kwh, 3),
            "unit_price":        m["unit_price"],
            "cost":              cost,
        })
    cost_tenant = total_cost_flat * eff_days / bd / n
    prepay      = prepay_monthly * 12 / 365 * eff_days
    nach        = cost_tenant - prepay
    if is_pauschale:
        nach = max(0.0, nach)
    return dict(
        total_units     = round(total_units, 3),
        total_cost_flat = round(total_cost_flat, 2),
        cost_tenant     = round(cost_tenant, 2),
        prepay          = round(prepay, 2),
        nach            = round(nach, 2),
        meter_details   = meter_details,
    )


def betriebskosten_calc(cost_flat, tenants, months, bk_start, bk_end, limit_per_month=206):
    num_months = (bk_end.year - bk_start.year) * 12 + (bk_end.month - bk_start.month + 1)
    if num_months == 0:
        num_months = 1
    cost_per_tenant = cost_flat / tenants
    period_cost = cost_per_tenant / num_months * months
    limit_month = limit_per_month / tenants
    limit_period = limit_month * months
    nachzahlung = period_cost - limit_period
    return cost_per_tenant, period_cost, limit_period, nachzahlung


def dashboard_stats():

    properties = fetch("SELECT COUNT(*) FROM properties")[0][0]
    apartments = fetch("SELECT COUNT(*) FROM apartments")[0][0]
    tenants = fetch("SELECT COUNT(*) FROM tenants")[0][0]
    contracts = fetch("SELECT COUNT(*) FROM contracts")[0][0]

    rent = fetch("SELECT SUM(rent) FROM contracts")[0][0]

    if rent is None:
        rent = 0

    return {
        "properties": properties,
        "apartments": apartments,
        "tenants": tenants,
        "contracts": contracts,
        "rent": rent,
    }


def detect_overdue(months_back=3):
    """
    For every active (non-terminated) contract, compare expected monthly rent
    against recorded payments for the last `months_back` months.
    Returns a list of dicts for contracts with at least one underpaid month.
    """
    today = _date.today()

    # Build the list of month start dates to examine (oldest first)
    months_to_check = []
    for i in range(months_back, 0, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months_to_check.append(_date(y, m, 1))

    active_contracts = fetch("""
        SELECT c.id, t.name, t.email, a.name, c.rent, c.start_date, c.end_date
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        WHERE COALESCE(c.terminated, 0) = 0
    """)

    results = []
    for cid, t_name, t_email, apt_name, rent, start_str, end_str in active_contracts:
        contract_start = _date.fromisoformat(start_str)
        contract_end   = (_date.fromisoformat(end_str)
                          if end_str and end_str != "None" else None)

        overdue_months = []
        total_due      = 0.0

        for m_start in months_to_check:
            m_end = m_start.replace(
                day=_calendar.monthrange(m_start.year, m_start.month)[1]
            )
            # Skip months before contract started or after it ended
            if contract_start > m_end:
                continue
            if contract_end and contract_end < m_start:
                continue

            paid = fetch("""
                SELECT COALESCE(SUM(amount), 0) FROM payments
                WHERE contract_id=? AND payment_date >= ? AND payment_date <= ?
            """, (cid, str(m_start), str(m_end)))[0][0]

            gap = round(rent - paid, 2)
            if gap > 0:
                overdue_months.append({
                    "month":    m_start.strftime("%B %Y"),
                    "expected": rent,
                    "paid":     paid,
                    "gap":      gap,
                })
                total_due += gap

        if overdue_months:
            results.append({
                "contract_id":    cid,
                "tenant":         t_name,
                "email":          t_email or "",
                "apartment":      apt_name,
                "overdue_months": overdue_months,
                "total_due":      round(total_due, 2),
            })

    return results


def tenant_ledger(tenant_id):

    payments = fetch(
        """
    SELECT amount, payment_date, COALESCE(payments.currency, 'EUR')
    FROM payments
    JOIN contracts ON payments.contract_id = contracts.id
    WHERE contracts.tenant_id = ?
    """,
        (tenant_id,),
    )

    return payments
