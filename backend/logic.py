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
from db import fetch, fetch_bundle, json_part

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
    if num_months <= 0:
        num_months = 1
    # A zero person count is a form left blank, not a flat nobody lives in —
    # the utilities above already treat it as one tenant.
    tenants = max(1, tenants)
    cost_per_tenant = cost_flat / tenants
    period_cost = cost_per_tenant / num_months * months
    limit_month = limit_per_month / tenants
    limit_period = limit_month * months
    nachzahlung = period_cost - limit_period
    return cost_per_tenant, period_cost, limit_period, nachzahlung


def detect_overdue(default_months_back=12, owner=None):
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
    expected total. Uses one query total regardless of contract/month count.
    """
    today = _date.today()
    cur_first = today.replace(day=1)
    end_first = _add_months(cur_first, -1)                 # last complete month
    default_start = _add_months(cur_first, -default_months_back)
    cur_ym = cur_first.strftime("%Y-%m")

    # Both reads go in one round trip. The payments side is not narrowed to the
    # look-back window: the window start depends on each contract's
    # rent_settled_until, which the other half of this very bundle carries, and
    # the bound would make the two reads sequential again. Nothing is lost —
    # every month is filtered against that contract's own window below, and the
    # grouped result is the same size with or without the bound.
    #
    # Money is carried as TEXT and parsed back to Decimal: json_build_array
    # would hand back floats, and rent arithmetic must not go near binary
    # floating point.
    #
    # Rent only: a Nebenkosten Nachzahlung is not rent, and counting it here
    # would hide a missed month; a refund would invent one. payment_date is ISO
    # text, so substr(...,1,7) is 'YYYY-MM'.
    #
    # Rent kept from the deposit counts too, in the month of the deduction —
    # whether the tenant did not pay (Mietrückstand) or you agreed they could
    # abwohnen. Tagged apart so the reminder can say how much came that way.
    from kaution_rules import NK_REF_TYPE, RENT_CATEGORIES
    loaded = fetch_bundle([
        json_part("contracts", """
            SELECT c.id, t.name, t.email, a.name, c.rent::text, c.start_date, c.end_date,
                   p.name, COALESCE(c.currency, 'EUR'), c.rent_settled_until
            FROM contracts c
            JOIN tenants t ON c.tenant_id = t.id
            JOIN apartments a ON c.apartment_id = a.id
            JOIN properties p ON a.property_id = p.id
            WHERE COALESCE(c.terminated, 0) = 0 AND c.owner_id = ?
            ORDER BY t.name
        """, (owner,)),
        ("paid", """
            SELECT json_build_array(p.contract_id, substr(p.payment_date, 1, 7), 0,
                                    COALESCE(SUM(p.amount), 0)::text)
            FROM payments p
            JOIN contracts c ON p.contract_id = c.id
            WHERE COALESCE(c.terminated, 0) = 0
              AND c.owner_id = ?
              AND p.kind = 'rent'
              AND p.payment_date <= ?
            GROUP BY p.contract_id, substr(p.payment_date, 1, 7)
            UNION ALL
            SELECT json_build_array(d.contract_id, substr(d.date, 1, 7), 1,
                                    COALESCE(SUM(d.amount), 0)::text)
            FROM kaution_deductions d
            JOIN contracts c ON d.contract_id = c.id
            WHERE COALESCE(c.terminated, 0) = 0
              AND c.owner_id = ?
              AND d.category IN (?, ?) AND COALESCE(d.reference_type, '') <> ?
              AND d.date <= ?
            GROUP BY d.contract_id, substr(d.date, 1, 7)
        """, (owner, str(today), owner, *RENT_CATEGORIES, NK_REF_TYPE, str(today))),
    ])
    contracts = [(*r[:4], Decimal(r[4]), *r[5:]) for r in loaded["contracts"]]
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

    paid_by: dict = {}
    deposit_by: dict = {}
    for cid, ym, from_deposit, total in loaded["paid"]:
        total = Decimal(total)
        paid_by[(cid, ym)] = paid_by.get((cid, ym), _ZERO) + total
        if from_deposit:
            deposit_by[(cid, ym)] = deposit_by.get((cid, ym), _ZERO) + total

    results = []
    for row in contracts:
        cid, t_name, t_email, apt_name, rent, start_str, end_str, prop_name, currency, settled = row
        # The API now refuses malformed dates, but a row that predates that
        # check must not take the whole reminders page down with it.
        try:
            contract_start = _date.fromisoformat(str(start_str))
            contract_end   = (_date.fromisoformat(str(end_str))
                              if end_str and str(end_str) != "None" else None)
        except ValueError:
            continue

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
        from_deposit = sum((v for (pc, ym), v in deposit_by.items()
                            if pc == cid and start_ym <= ym <= cur_ym), _ZERO)

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
            "paid_from_deposit": float(round(from_deposit, 2)),
            "balance":           float(round(balance, 2)),
            "amount_due":        float(round(amount_due, 2)),
            "current_month_paid": float(paid_by.get((cid, cur_ym), _ZERO)),
            "months_due":        months_due,
            "months":            month_rows,
        })

    return results



# ── What a meter's consumption costs over a period ───────────────────────────

def reading_on(readings, on_date: str):
    """The meter's value on `on_date`, and where the number came from.

    `readings` is [(date, value), ...] in any order. A date that was actually
    read gives ("measured", value). Between two readings the value is
    interpolated — a meter runs on while nobody reads it. Outside the
    readings, it is extrapolated from the average daily rate of the whole
    series, which is an estimate and says so.

    Returns (value, source) or (None, "no_readings").
    """
    rs = sorted(((str(d), float(v)) for d, v in readings if d), key=lambda x: x[0])
    if not rs:
        return None, "no_readings"
    if len(rs) == 1:
        return rs[0][1], "measured" if rs[0][0] == on_date else "extrapolated"

    for d, v in rs:
        if d == on_date:
            return v, "measured"

    def days_between(a: str, b: str) -> int:
        return (_date.fromisoformat(b) - _date.fromisoformat(a)).days

    if rs[0][0] < on_date < rs[-1][0]:
        before = max((r for r in rs if r[0] < on_date), key=lambda r: r[0])
        after = min((r for r in rs if r[0] > on_date), key=lambda r: r[0])
        span = days_between(before[0], after[0])
        if span <= 0:
            return before[1], "measured"
        share = days_between(before[0], on_date) / span
        return before[1] + (after[1] - before[1]) * share, "interpolated"

    # Outside the measured window: carry the average rate forwards or back.
    total_days = days_between(rs[0][0], rs[-1][0])
    per_day = (rs[-1][1] - rs[0][1]) / total_days if total_days > 0 else 0.0
    edge = rs[-1] if on_date > rs[-1][0] else rs[0]
    return edge[1] + per_day * days_between(edge[0], on_date), "extrapolated"


def estimate_utility_cost(readings, start_date: str, end_date: str,
                          arbeitspreis: float, grundpreis_monthly: float = 0.0,
                          conversion_factor: float = 1.0) -> dict:
    """What a meter's consumption over [start_date, end_date] costs.

    consumption × conversion_factor × Arbeitspreis, plus the Grundpreis for
    the days in the period. The Grundpreis is prorated by day exactly as the
    Nebenkostenabrechnung does it (monthly × 12 ÷ 365), so an estimate and a
    later Abrechnung of the same period agree.

    `conversion_factor` turns meter units into billed units — gas is metered
    in m³ and billed in kWh (Zustandszahl × Brennwert).
    """
    if end_date < start_date:
        raise ValueError("end_date must not be before start_date")
    start_value, start_src = reading_on(readings, start_date)
    end_value, end_src = reading_on(readings, end_date)
    if start_value is None or end_value is None:
        return {"readings": 0, "source": "no_readings"}

    days = (_date.fromisoformat(end_date) - _date.fromisoformat(start_date)).days + 1
    consumption = end_value - start_value
    billed_units = consumption * (conversion_factor or 1.0)
    arbeitskosten = billed_units * arbeitspreis
    grundkosten = grundpreis_monthly * 12 / 365 * days
    total = arbeitskosten + grundkosten
    return {
        "readings": len(readings),
        # A meter does not run backwards. A falling count means the meter was
        # exchanged (the new one starts at zero) or a reading was mistyped, and
        # either way end − start is not a consumption: it produces a negative
        # Arbeitskosten that silently discounts the bill. The figures are still
        # returned — seeing them is how the bad reading gets found — but they
        # are flagged so nothing presents this as a cost.
        "decreasing": consumption < 0,
        "start_value": round(start_value, 3), "start_source": start_src,
        "end_value": round(end_value, 3), "end_source": end_src,
        "consumption": round(consumption, 3),
        "billed_units": round(billed_units, 3),
        "conversion_factor": conversion_factor or 1.0,
        "days": days,
        "arbeitskosten": round(arbeitskosten, 2),
        "grundkosten": round(grundkosten, 2),
        "total": round(total, 2),
        "per_month": round(total / days * 365 / 12, 2) if days else 0.0,
        # An estimate only where a bound had to be derived.
        "estimated": start_src != "measured" or end_src != "measured",
    }


# ── A meter only ever counts up ──────────────────────────────────────────────
# Readings are cumulative: the number on the dial cannot fall. A lower one is
# almost always a typo — Vattenfall prints its figures without the decimals, so
# a whole number copied off the invoice reads as a drop of up to a full unit —
# or a meter that was exchanged, which belongs in a new meter record rather
# than a backwards reading on the old one.
#
# Caught at entry it is one corrected digit. Left in, every downstream figure
# built on it is wrong: a negative consumption becomes a negative Arbeitskosten
# that quietly discounts the bill, and the Nebenkostenabrechnung interpolates
# from it.

# Readings are stored to three decimals, so anything under half a thousandth is
# the same number written differently, not a meter running backwards.
_READING_EPS = 0.0005

# What each meter counts, for the refusal message. A Heizkostenverteiler counts
# in whatever unit its own `unit_label` says, so it is left unnamed here.
METERED_UNITS = {"strom": "kWh", "gas": "m³", "wasser": "m³", "heizung": ""}


def reading_conflict(reading, before=None, after=None):
    """Why `reading` cannot sit between its neighbours, or None if it can.

    `before` and `after` are the nearest (date, value) recorded on either side,
    or None where there is none. Returns ("below_previous"|"above_next", date,
    value) — the caller phrases the message; the comparison lives here so it
    can be tested without a database.

    An unchanged meter is fine: only a strict fall below the previous reading,
    or a rise above a later one, is a conflict.
    """
    value = float(reading)
    if before is not None and value < float(before[1]) - _READING_EPS:
        return ("below_previous", before[0], float(before[1]))
    if after is not None and value > float(after[1]) + _READING_EPS:
        return ("above_next", after[0], float(after[1]))
    return None


def _fmt_reading(value: float) -> str:
    """A reading without the trailing zeros the NUMERIC(.,3) column stores."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def reading_neighbours(meter_type: str, meter_id: int, reading_date: str, owner: int):
    """The nearest readings strictly before and strictly after `reading_date`
    for this meter, as (date, value) or None — in one round trip.

    A reading already standing on the same date is neither: it is the row being
    replaced, and whether the new value differs from it is not a conflict.
    """
    parts = fetch_bundle([
        json_part("before",
                  "SELECT reading_date, reading FROM meter_readings "
                  "WHERE meter_type=? AND meter_id=? AND owner_id=? AND reading_date < ? "
                  "ORDER BY reading_date DESC, id DESC LIMIT 1",
                  (meter_type, meter_id, owner, reading_date)),
        json_part("after",
                  "SELECT reading_date, reading FROM meter_readings "
                  "WHERE meter_type=? AND meter_id=? AND owner_id=? AND reading_date > ? "
                  "ORDER BY reading_date ASC, id ASC LIMIT 1",
                  (meter_type, meter_id, owner, reading_date)),
    ])
    before = tuple(parts["before"][0]) if parts["before"] else None
    after = tuple(parts["after"][0]) if parts["after"] else None
    return before, after


def reading_rejection(meter_type: str, meter_id: int, reading_date: str, reading,
                      owner: int) -> str | None:
    """The message refusing this reading, or None when it is acceptable.

    Returns a string rather than raising, so the HTTP layer owns the status code
    and this stays testable on its own.
    """
    before, after = reading_neighbours(meter_type, meter_id, reading_date, owner)
    conflict = reading_conflict(reading, before, after)
    if not conflict:
        return None
    kind, when, value = conflict
    unit = METERED_UNITS.get(meter_type, "")
    suffix = f" {unit}" if unit else ""
    got = _fmt_reading(float(reading))
    had = _fmt_reading(value)
    if kind == "below_previous":
        return (f"A meter only counts up, but {got}{suffix} is below the {had}{suffix} "
                f"already recorded on {when}. Check the digits after the decimal point — "
                f"a figure copied from the provider's invoice often leaves them off. If the "
                f"meter was exchanged, add the replacement as a new meter instead of a lower "
                f"reading on this one.")
    return (f"A meter only counts up, but {got}{suffix} is above the {had}{suffix} already "
            f"recorded later, on {when}. Check the digits after the decimal point, and that "
            f"this reading is dated the day it was taken.")
