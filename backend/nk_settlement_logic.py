"""Rules around the Nebenkostenabrechnung a landlord sends a tenant.

Pure functions, no database: the router loads rows and hands them in.

The deadline is §556 Abs. 3 BGB. The Abrechnung has to reach the tenant by the
end of the twelfth month after the billing period ends. Miss it and a
Nachzahlung can no longer be claimed, although a Guthaben is still owed. So a
settlement that is late is not merely untidy; it is money lost.
"""
import calendar
from datetime import date

# How long a missed deadline keeps showing. Past this, a reminder is noise
# rather than something that can still be acted on.
MISSED_GRACE_DAYS = 90


def _parse(value) -> date | None:
    if not value or str(value) == "None":
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def abrechnung_deadline(period_end: date) -> date:
    """The last day the Abrechnung may reach the tenant (§556 Abs. 3 BGB):
    twelve months after the billing period ends. A period ending on a month's
    last day ends its deadline on a month's last day too, so 29 Feb carries
    to 28 Feb rather than to 1 March."""
    d = add_months(period_end, 12)
    if period_end.day == calendar.monthrange(period_end.year, period_end.month)[1]:
        d = d.replace(day=calendar.monthrange(d.year, d.month)[1])
    return d


def settlement_state(amount: float, paid: float) -> tuple[float, str]:
    """(still open, status) for a settlement of `amount` with `paid` booked
    against it. Both are signed the same way: a Nachzahlung is positive and
    the tenant's transfer is positive; a Guthaben is negative and the refund
    you send is negative."""
    open_ = round(float(amount) - float(paid), 2)
    if abs(open_) < 0.005:
        return 0.0, "settled"
    return open_, ("partial" if abs(float(paid)) >= 0.005 else "open")


def _overlaps(a_start: date, a_end: date | None, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and (a_end is None or a_end >= b_start)


def pending_abrechnungen(contracts, settlements, today: date,
                         grace_days: int = MISSED_GRACE_DAYS) -> list[dict]:
    """Calendar years that still need an Abrechnung for a tenancy.

    contracts:   (id, tenant_id, apartment_id, start_date, end_date, nk_prepayment)
    settlements: (contract_id, period_start, period_end)

    A tenancy is a tenant in a flat, not a contract: a rent change is recorded
    as a follow-on contract, and one Abrechnung covers both. Only contracts
    with an NK prepayment count; a flat without one has nothing to settle.

    Billing periods are assumed to be calendar years, which is the common
    case and what the Hausgeldabrechnung uses. A settlement for any period
    overlapping the year covers it, so an off-calendar period still clears
    the reminder.
    """
    group_of: dict[int, tuple] = {}
    groups: dict[tuple, list] = {}
    for cid, tenant_id, apt_id, start, end, nk in contracts:
        key = (tenant_id, apt_id)
        group_of[cid] = key
        s, e = _parse(start), _parse(end)
        if s is None or not nk or float(nk) <= 0:
            continue
        groups.setdefault(key, []).append((cid, s, e))

    covered: dict[tuple, list] = {}
    for cid, ps, pe in settlements:
        key = group_of.get(cid)
        s, e = _parse(ps), _parse(pe)
        if key is not None and s and e:
            covered.setdefault(key, []).append((s, e))

    out = []
    for key, members in groups.items():
        first_year = min(s.year for _, s, _ in members)
        for year in range(first_year, today.year):
            y_start, y_end = date(year, 1, 1), date(year, 12, 31)
            active = [(cid, s, e) for cid, s, e in members
                      if _overlaps(s, e, y_start, y_end)]
            if not active:
                continue
            deadline = abrechnung_deadline(y_end)
            days = (deadline - today).days
            if days < -grace_days:
                continue
            if any(_overlaps(s, e, y_start, y_end) for s, e in covered.get(key, [])):
                continue
            # Point at the contract that was running at the end of the year —
            # the one the Abrechnung will be written against.
            cid = max(active, key=lambda r: r[1])[0]
            out.append({"contract_id": cid, "year": year,
                        "period_start": str(y_start), "period_end": str(y_end),
                        "deadline": str(deadline), "days_remaining": days,
                        "level": "missed" if days < 0 else "due"})
    out.sort(key=lambda r: (r["days_remaining"], r["contract_id"]))
    return out
