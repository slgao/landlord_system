"""Who has lived in one flat or WG room — and what the empty months cost.

The rest of the application looks at a tenancy and asks what is owed now. This
module looks at a *unit* and asks what has happened to it: every tenant it has
had, how long each stayed, what the rent did across the handovers, and the gaps
in between.

Three things decide whether the answers are right.

**A WG room is a unit of its own.** Rooms are siblings when they share
`(property_id, flat)` — the same grouping `/contracts/{id}/occupancy` uses to
decide how many people split the utilities. So the history of a room is the
contracts on that one `apartments` row, and the flat's other rooms are context
beside it, never mixed in.

**`end_date` draws the timeline; `terminated` only says whether it is live.**
The two disagree in real data: a contract can carry an end date without the
flag (a notice already served, a fixed term running out) or the flag without a
date. Placing a tenancy on a timeline needs a date, so the date wins; the flag
decides only whether an undated tenancy is still running, and when it says a
tenancy is over without saying when, the row admits it rather than inventing a
day.

**Occupancy is counted in days, tenancy length in months.** A vacancy of three
weeks is not a month, and rounding it to one would overstate every gap; but a
tenancy that began on the 20th owed rent for that whole month (§556b BGB), and
`rent_periods.months_in_year` already counts it as one. Different questions,
different units — mixing them is how an occupancy figure ends up above 100 %.
"""
from __future__ import annotations

from datetime import date as _date, timedelta as _day

UPCOMING, CURRENT, PAST = "upcoming", "current", "past"

_ONE_DAY = _day(days=1)


def _blank(v) -> bool:
    """Date columns are TEXT and a few legacy rows hold the string 'None'."""
    return v is None or str(v) in ("None", "")


def _dt(v):
    """An ISO date column as a date, or None when it holds nothing usable.

    Unparseable is treated as absent on purpose: a tenancy with a broken start
    date must not be placed on the timeline at all, because a string that
    sorts oddly would silently reorder the history around it.
    """
    if _blank(v):
        return None
    try:
        return _date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _f(v):
    return None if v is None else float(v)


def status_of(start, end, terminated, today: _date) -> str:
    """Whether a tenancy is still to come, running, or over.

    `end_date` decides wherever there is one — a tenancy whose term ran out
    last year is past whether or not anybody ticked the flag. Only when there
    is no end date does `terminated` get a say.
    """
    if start is None:
        return PAST
    if start > today:
        return UPCOMING
    if end is None:
        return PAST if terminated else CURRENT
    return CURRENT if end >= today else PAST


def months_running(start: _date, end: _date) -> int:
    """Calendar months a tenancy was running in, both ends counted.

    The convention `rent_periods.months_in_year` already uses: rent is owed
    monthly in advance, so a month the tenancy ran in at all is a month it was
    let for. A term of 1 Sep to 31 Aug is twelve months; one day into
    September makes it thirteen, because September's rent fell due.
    """
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _merge(spans: list[tuple[_date, _date]]) -> list[list[_date]]:
    """The union of inclusive day spans, earliest first.

    Spans a day apart are joined: one tenant leaving on 31 August and the next
    arriving on 1 September is continuous letting, not a vacancy of zero days.
    Overlaps are absorbed rather than counted twice, so two contracts entered
    for the same room over the same weeks cannot push occupancy past 100 %.
    """
    out: list[list[_date]] = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1] + _ONE_DAY:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def build(contracts: list[dict], today: _date) -> dict:
    """The history of one unit: a row per tenancy, and what they add up to.

    Each entry of `contracts` carries the stored columns plus `schedule`, the
    `RentSchedule` of that tenancy. Returns `{"tenancies": [...], "summary":
    {...}}` with the tenancies newest first — the current tenant is the one
    being looked for most of the time — and each `gap_days_before` measured
    against the tenancy that came before it in time.
    """
    rows = []
    for c in contracts:
        start = _dt(c.get("start_date"))
        end = _dt(c.get("end_date"))
        terminated = bool(c.get("terminated"))
        status = status_of(start, end, terminated, today)

        # Two different ends, and conflating them is how a tenant who moved in
        # last month comes to have "stayed" a year.
        #
        # `reach` is the term as contracted — how far the tenancy is agreed to
        # run. Gaps are measured against it, because a tenancy ending in March
        # followed by one starting in April is a handover, not six months of
        # vacancy just because March has not arrived yet.
        #
        # `lived` stops at today. How long somebody has stayed, and what they
        # pay now, are facts about time already passed: reading the rent at a
        # contracted end would quote a Staffel step (§557a) years before it is
        # owed, and a term of a year would be reported as a year lived on the
        # day the tenant moved in.
        reach = end if end is not None else (today if start else None)
        if reach is not None and start is not None and reach < start:
            reach = start
        lived = min(reach, today) if reach is not None else None

        schedule = c.get("schedule")
        rent_at_end = None
        nkv_at_end = None
        if schedule and lived is not None:
            rent_at_end = schedule.on(lived.isoformat()) or schedule.first()
            nkv_at_end = schedule.nkv_on(lived.isoformat())

        rows.append({
            "contract_id": c.get("contract_id"),
            "tenant_id": c.get("tenant_id"),
            "tenant_name": c.get("tenant_name"),
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "end_known": end is not None,
            "terminated": terminated,
            "status": status,
            "months": (months_running(start, lived)
                       if start and lived and status != UPCOMING else None),
            # Both from the tenancy's *first* period, so the pair is the price
            # it was signed at — the figure §551 measures the deposit against.
            "rent_start": _f(schedule.first()) if schedule else None,
            "nkv_start": _f(schedule.periods[0][2]) if schedule else None,
            "rent_end": _f(rent_at_end),
            "nkv_end": _f(nkv_at_end),
            "rent_changes": max(0, len(schedule) - 1) if schedule else 0,
            "kaution_amount": _f(c.get("kaution_amount")),
            "kaution_currency": (c.get("kaution_currency") or "EUR").upper(),
            "kaution_returned": _f(c.get("kaution_returned")),
            "kaution_returned_date": (None if _blank(c.get("kaution_returned_date"))
                                      else str(c.get("kaution_returned_date"))),
            "co_tenants": list(c.get("co_tenants") or []),
            "handovers": list(c.get("handovers") or []),
            "gap_days_before": None,
            "_start": start,
            "_reach": reach,
        })

    # Gaps are read in time order; an undated tenancy cannot be placed, so it
    # sits at the end and takes part in no gap arithmetic.
    placed = sorted((r for r in rows if r["_start"]), key=lambda r: r["_start"])
    for previous, this in zip(placed, placed[1:]):
        if previous["_reach"] is None:
            continue
        gap = (this["_start"] - previous["_reach"]).days - 1
        this["gap_days_before"] = max(0, gap)

    summary = _summarise(placed, today)
    # Every tenancy counts in the total, including one too broken to place.
    summary["tenancies"] = len(rows)
    summary["undated"] = len(rows) - len(placed)

    # Newest first, undated last: a panel is opened to see who is there now.
    rows.sort(key=lambda r: (r["_start"] is not None, r["_start"] or _date.min),
              reverse=True)
    for r in rows:
        del r["_start"], r["_reach"]
    return {"tenancies": rows, "summary": summary}


def _summarise(placed: list[dict], today: _date) -> dict:
    """The figures above the list: how much of the time the unit earned, how
    long tenants stay, and what the rent has done across the handovers."""
    out = {
        "tenancies": len(placed), "completed": 0, "upcoming": 0,
        "first_start": None, "vacant_since": None,
        "span_days": None, "let_days": None, "vacant_days": None,
        "occupancy_pct": None, "longest_gap_days": None,
        "avg_tenancy_months": None,
        "rent_first": None, "rent_now": None,
    }
    if not placed:
        return out

    started = [r for r in placed if r["status"] != UPCOMING]
    completed = [r for r in started if r["status"] == PAST]
    out["upcoming"] = len(placed) - len(started)
    out["completed"] = len(completed)
    out["first_start"] = placed[0]["start_date"]

    if completed:
        lengths = [r["months"] for r in completed if r["months"] is not None]
        if lengths:
            out["avg_tenancy_months"] = round(sum(lengths) / len(lengths), 1)

    # The rent the unit first went out at, and what it stands at now — the
    # progression a Mietspiegel comparison starts from.
    first_rent = next((r["rent_start"] for r in placed if r["rent_start"]), None)
    live = [r for r in placed if r["status"] == CURRENT]
    latest = live[-1] if live else (started[-1] if started else None)
    out["rent_first"] = first_rent
    out["rent_now"] = latest["rent_end"] if latest else None

    # Occupancy runs from the first move-in to today. A tenancy still to come
    # contributes nothing: counting a term that has not begun as time let
    # would report a room as earning before anybody held the keys.
    if not started:
        return out
    span_start = started[0]["_start"]
    if span_start > today:
        return out
    spans = []
    for r in started:
        end = min(r["_reach"], today) if r["_reach"] else today
        if end >= r["_start"]:
            spans.append((r["_start"], end))
    merged = _merge(spans)
    let_days = sum((e - s).days + 1 for s, e in merged)
    span_days = (today - span_start).days + 1
    out["span_days"] = span_days
    out["let_days"] = let_days
    out["vacant_days"] = max(0, span_days - let_days)
    out["occupancy_pct"] = round(100.0 * let_days / span_days, 1)

    # The longest the unit has stood empty — the stretch still running
    # included. A room let for four months two years ago and empty ever since
    # has its worst gap *after* the last tenancy rather than between two of
    # them, so measuring only the gaps between tenancies would report none.
    stretches = [(later[0] - earlier[1]).days - 1
                 for earlier, later in zip(merged, merged[1:])]
    trailing = (today - merged[-1][1]).days if merged else 0
    if trailing > 0:
        stretches.append(trailing)
        out["vacant_since"] = (merged[-1][1] + _ONE_DAY).isoformat()
    out["longest_gap_days"] = max(stretches) if stretches else 0
    return out
