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
import math as _math
from datetime import date as _date
from decimal import Decimal
from db import fetch

_ZERO = Decimal("0")


def _month_first(d):
    """First day of d's month."""
    return d.replace(day=1)


def _add_months(first_of_month, delta):
    """Shift a day-1 date by `delta` whole months (delta may be negative)."""
    idx = first_of_month.year * 12 + (first_of_month.month - 1) + delta
    y, m = divmod(idx, 12)
    return _date(y, m + 1, 1)


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
    prepay             = prepay_monthly * 12 / 365 * eff_days / n
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
    prepay             = prepay_monthly * 12 / 365 * eff_days / n
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
    prepay         = prepay_monthly * 12 / 365 * eff_days / n
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
    prepay      = prepay_monthly * 12 / 365 * eff_days / n
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
    prepay      = prepay_monthly * 12 / 365 * eff_days / n
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


def sum_cost_calc(cost_flat, num_tenants, bill_days, eff_days, prepay_monthly,
                  is_pauschale=False):
    """
    Direct total-cost calculation for any utility (Strom/Gas/Kaltwasser/
    Warmwasser/Heizkosten) when the provider's bill already states the total
    cost for the flat over the billing period — no meter readings needed.

    cost_flat       – total cost for the whole flat over the billing period
    bill_days       – length of the provider's billing period in days
    eff_days        – days the tenant actually lived in the flat
    prepay_monthly  – the tenant's monthly prepayment (Vorauszahlung)
    """
    n  = max(1, num_tenants)
    bd = max(1, bill_days)
    cost_tenant = cost_flat * eff_days / bd / n
    prepay      = prepay_monthly * 12 / 365 * eff_days / n
    nach        = cost_tenant - prepay
    if is_pauschale:
        nach = max(0.0, nach)
    return dict(
        cost_flat   = round(cost_flat, 2),
        cost_tenant = round(cost_tenant, 2),
        prepay      = round(prepay, 2),
        nach        = round(nach, 2),
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


def detect_overdue(default_months_back=12):
    """
    For every active (non-terminated) contract, compare the total rent due over
    a look-back window against the total recorded payments in that window, using
    a *cumulative balance* (not independent per-month checks). This means:

      • A payment made before the month it covers still counts (it falls inside
        the window), so paying rent early is not flagged as a gap.
      • Overpaying one month offsets an earlier shortfall (e.g. a double payment
        after a missed month nets to zero), so it is not flagged either.
      • Payments recorded in the current (incomplete) month count as credit
        against arrears, so catching up clears the reminder.

    Per-contract window start:
      • If the contract has `rent_settled_until` set, evaluation starts the month
        AFTER it (everything up to that date is assumed settled — handy when old
        payments were never entered).
      • Otherwise it starts `default_months_back` months before the current month.

    Only complete months (up to and including last month) count toward the
    expected total. Uses two queries total regardless of contract/month count.
    """
    today = _date.today()
    cur_first = today.replace(day=1)
    end_first = _add_months(cur_first, -1)                 # last complete month
    default_start = _add_months(cur_first, -default_months_back)
    cur_ym = cur_first.strftime("%Y-%m")

    contracts = fetch("""
        SELECT c.id, t.name, t.email, a.name, c.rent, c.start_date, c.end_date,
               p.name, COALESCE(c.currency, 'EUR'), c.rent_settled_until
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE COALESCE(c.terminated, 0) = 0
        ORDER BY t.name
    """)
    if not contracts:
        return []

    # Resolve each contract's window start (month-1 date).
    starts = {}
    for row in contracts:
        cid, settled = row[0], row[9]
        s = None
        if settled and str(settled) != "None":
            try:
                s = _date.fromisoformat(settled)
            except ValueError:
                s = None
        starts[cid] = _add_months(_month_first(s), 1) if s else default_start

    # One grouped query: payments summed per (contract, calendar month) from the
    # earliest needed month through today. payment_date is ISO text, so
    # substr(...,1,7) is 'YYYY-MM'.
    min_start = min(starts.values())
    paid_rows = fetch("""
        SELECT p.contract_id, substr(p.payment_date, 1, 7), COALESCE(SUM(p.amount), 0)
        FROM payments p
        JOIN contracts c ON p.contract_id = c.id
        WHERE COALESCE(c.terminated, 0) = 0
          AND p.payment_date >= ? AND p.payment_date <= ?
        GROUP BY p.contract_id, substr(p.payment_date, 1, 7)
    """, (str(min_start), str(today)))
    paid_by = {(cid, ym): total for cid, ym, total in paid_rows}

    results = []
    for row in contracts:
        cid, t_name, t_email, apt_name, rent, start_str, end_str, prop_name, currency, settled = row
        contract_start = _date.fromisoformat(start_str)
        contract_end   = (_date.fromisoformat(end_str)
                          if end_str and str(end_str) != "None" else None)

        # Complete months in [window start, last complete month] the contract is active.
        months = []
        m = starts[cid]
        while m <= end_first:
            m_end = m.replace(day=_calendar.monthrange(m.year, m.month)[1])
            if not (contract_start > m_end or (contract_end and contract_end < m)):
                months.append(m)
            m = _add_months(m, 1)
        if not months:
            continue

        expected_total = rent * len(months)

        # Total paid across the window, INCLUDING the current (incomplete) month
        # so pre-payments and catch-up payments count as credit.
        start_ym = starts[cid].strftime("%Y-%m")
        paid_total = _ZERO
        for (pc, ym), val in paid_by.items():
            if pc == cid and start_ym <= ym <= cur_ym:
                paid_total += val

        balance = paid_total - expected_total
        amount_due = -balance
        if amount_due <= Decimal("0.005"):
            continue

        # Per-month breakdown with a running balance, for verification in the UI.
        month_rows = []
        running = _ZERO
        for mm in months:
            pm = paid_by.get((cid, mm.strftime("%Y-%m")), _ZERO)
            running += pm - rent
            month_rows.append({
                "month":         mm.strftime("%B %Y"),
                "expected":      float(rent),
                "paid":          float(pm),
                "balance_after": float(round(running, 2)),
            })

        rent_f = float(rent)
        months_due = _math.ceil(float(amount_due) / rent_f) if rent_f > 0 else len(months)
        results.append({
            "contract_id":       cid,
            "tenant":            t_name,
            "email":             t_email or "",
            "apartment":         apt_name,
            "property_name":     prop_name,
            "currency":          currency,
            "rent":              rent_f,
            "settled_until":     settled if (settled and str(settled) != "None") else None,
            "first_month":       months[0].strftime("%B %Y"),
            "last_month":        months[-1].strftime("%B %Y"),
            "expected_total":    float(round(expected_total, 2)),
            "paid_total":        float(round(paid_total, 2)),
            "balance":           float(round(balance, 2)),
            "amount_due":        float(round(amount_due, 2)),
            "current_month_paid": float(paid_by.get((cid, cur_ym), _ZERO)),
            "months_due":        months_due,
            "months":            month_rows,
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
