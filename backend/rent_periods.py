"""What a tenancy costs, period by period — and which period a month falls in.

The rent of a tenancy is not one number. It is raised under §558 BGB, stepped
under a Staffelmiete (§557a), tracked to the index under an Indexmiete
(§557b), or renegotiated after a modernisation (§559). Each of those is the
*same* tenancy at a new price from a given date, exactly as a Hausgeld of 310 €
becoming 348,50 € is the same cost with a new price.

Before this module there was one `contracts.rent`, used for every month of the
tenancy. Recording an increase therefore restated the past: raising the rent
from 1.050 € to 1.150 € changed what was expected in all twelve months of a
filed tax year, and with it the arrears history and every Mahnung built on it.

So the periods are the record, and this is the one rule that reads them:

    the rent in force on the first day of a month is the rent for that month.

Rent is due monthly in advance (§556b BGB), so a month is charged at the price
agreed when it began. A change dated mid-month therefore takes effect the
following month, which is also what §558 Abs. 2 produces on its own: an
increase is owed from the beginning of the third calendar month after the
demand arrives.
"""
from __future__ import annotations

from decimal import Decimal

_ZERO = Decimal("0")

# Why this price, which is the part a tenant can dispute and the landlord has
# to be able to show. 'initial' is what the contract was signed at.
KINDS = ("initial", "agreed", "staffel", "index", "modernisation")

KIND_LABELS = {
    "initial": "Vertragsbeginn",
    "agreed": "Mieterhöhung (§558 BGB)",
    "staffel": "Staffelmiete (§557a BGB)",
    "index": "Indexmiete (§557b BGB)",
    "modernisation": "Modernisierungsumlage (§559 BGB)",
}


def _blank(v) -> bool:
    """Date columns are TEXT and a few legacy rows hold the string 'None'."""
    return v is None or str(v) in ("None", "")


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v or 0))


class RentSchedule:
    """The agreed prices of one tenancy, in date order.

    Built from rows of (valid_from, rent, nebenkosten_vorauszahlung), where
    valid_from is the first day the price applies. A period runs until the next
    one starts; the last runs until the tenancy ends.
    """

    __slots__ = ("periods",)

    def __init__(self, rows=()):
        cleaned = []
        for row in rows:
            valid_from, rent = row[0], row[1]
            nkv = row[2] if len(row) > 2 else None
            cleaned.append((("" if _blank(valid_from) else str(valid_from)),
                            _dec(rent),
                            None if nkv is None else _dec(nkv)))
        # A blank valid_from sorts first: it has always been in force.
        self.periods = sorted(cleaned, key=lambda p: p[0])

    def __bool__(self) -> bool:
        return bool(self.periods)

    def __len__(self) -> int:
        return len(self.periods)

    def _at(self, on_date: str):
        """The period in force on `on_date`, or None when none had started."""
        found = None
        for valid_from, rent, nkv in self.periods:
            if valid_from and valid_from > str(on_date):
                break
            found = (valid_from, rent, nkv)
        return found

    def on(self, on_date: str) -> Decimal:
        """The rent in force on a day — zero before the first period starts."""
        hit = self._at(on_date)
        return hit[1] if hit else _ZERO

    def nkv_on(self, on_date: str):
        """The Nebenkosten prepayment in force, or None when never recorded."""
        hit = self._at(on_date)
        return hit[2] if hit else None

    def for_month(self, month_first: str) -> Decimal:
        """The price that applied during a month the tenancy was running in.

        Normally the price in force on the first of the month. A tenancy that
        began mid-month has its first period dated that day, so asking for the
        first would answer "nothing agreed yet" and lose the month: there the
        answer is the price the tenancy started at.

        Callers filter by the contract's own dates first, so a month before
        the tenancy began is never asked about.
        """
        if not self.periods:
            return _ZERO
        first_start = self.periods[0][0]
        if first_start and first_start > str(month_first):
            return self.periods[0][1]
        return self.on(month_first)

    def first(self) -> Decimal:
        return self.periods[0][1] if self.periods else _ZERO

    def changes_after(self, on_date: str):
        """Periods that have not started yet, soonest first — a Staffel step
        or an agreed increase that is on file but not yet owed."""
        return [p for p in self.periods if p[0] and p[0] > str(on_date)]


def rent_at(value, on_date: str) -> Decimal:
    """The rent of a tenancy on a day, from a schedule or a plain amount.

    Both are accepted because the readers are shared with callers that have
    only ever had one figure to work with — a test, or a caller resolving the
    rent itself. A plain amount is the same in every month, which is precisely
    the behaviour this module exists to replace, so it is never the shape the
    application passes.
    """
    if isinstance(value, RentSchedule):
        return value.on(on_date)
    return _dec(value)


def rent_for_month(value, month_first: str) -> Decimal:
    """The rent of a tenancy for a whole month, from a schedule or an amount."""
    if isinstance(value, RentSchedule):
        return value.for_month(month_first)
    return _dec(value)


def schedules_from_rows(rows) -> dict:
    """{contract_id: RentSchedule} from rows of
    (contract_id, valid_from, rent, nebenkosten_vorauszahlung)."""
    by_contract: dict = {}
    for cid, valid_from, rent, nkv in rows:
        by_contract.setdefault(cid, []).append((valid_from, rent, nkv))
    return {cid: RentSchedule(rs) for cid, rs in by_contract.items()}


def kaution_cap(cold_rent) -> Decimal:
    """The most a deposit may be, under §551 Abs. 1 BGB: three months' rent.

    Three *Kaltmieten* — the rent without the Nebenkosten prepayment. A deposit
    agreed above the cap is not void; the excess is simply not owed, and the
    tenant can reclaim it, so a tool that knows the Kaltmiete should say so
    rather than let it pass unremarked.
    """
    return (_dec(cold_rent) * 3).quantize(Decimal("0.01"))


def cold_rent(rent, nkv) -> Decimal:
    """Kaltmiete: what is left of the rent once the Nebenkosten share is out."""
    return _dec(rent) - _dec(nkv)


def load_schedules(owner) -> dict:
    """{contract_id: RentSchedule} for one landlord, in one query.

    Here rather than in each reader, because every report that states what a
    month was expected to earn has to resolve rent the same way.
    """
    from db import fetch
    return schedules_from_rows(fetch(
        "SELECT contract_id, valid_from, rent, nebenkosten_vorauszahlung "
        "FROM contract_rents WHERE owner_id = ? ORDER BY valid_from", (owner,)))


def months_in_year(start_date, end_date, year: int):
    """The first of each month of `year` that the tenancy was running in.

    Month granularity, matching tax_logic.months_active_in_year: a tenancy
    that began on the 20th still counts that month, because the Anlage V is
    filed per month and the rent for it was owed.
    """
    from datetime import date as _d
    out = []
    for m in range(1, 13):
        first = _d(year, m, 1)
        last = _d(year + (m == 12), (m % 12) + 1, 1)
        if not _blank(start_date) and str(start_date) >= str(last):
            continue
        if not _blank(end_date) and str(end_date) < str(first):
            continue
        out.append(first.isoformat())
    return out


def year_total(schedule, start_date, end_date, year: int):
    """(months, total rent) for one tenancy in one tax year.

    Summed month by month at the price in force when each began, so a year in
    which the rent was raised reports what was actually owed rather than
    twelve times whichever figure the contract happens to carry now.
    """
    months = months_in_year(start_date, end_date, year)
    total = sum((rent_for_month(schedule, m) for m in months), _ZERO)
    return len(months), total


# ── §558 BGB: what an ordinary rent increase has to satisfy ─────────────────
#
# These are checks, not refusals. Every one of them has lawful exceptions —
# a modernisation surcharge under §559 is not bound by the Kappungsgrenze, an
# Indexmiete follows the index on its own schedule, a Staffel is agreed once
# and owed in full — and a tool that blocked the entry would simply be wrong
# about somebody's tenancy. Saying what looks off, with the paragraph, leaves
# the judgement where it belongs.

# The cap on how far rent may rise within three years. 20 % generally; 15 %
# where a Land has made a Kappungsgrenzenverordnung, which Berlin and most
# larger cities have. Which applies depends on the municipality, so the
# warning names both rather than pretending to know.
KAPPUNGSGRENZE_GENERAL = Decimal("0.20")
KAPPUNGSGRENZE_TIGHT = Decimal("0.15")

# §558 Abs. 1: the rent must have been unchanged for twelve months when the
# demand is made, and the new rent is owed at the earliest fifteen months
# after the last increase took effect.
WARTEFRIST_MONTHS = 15


def _months_between(earlier: str, later: str) -> int:
    from datetime import date as _d
    a, b = _d.fromisoformat(str(earlier)[:10]), _d.fromisoformat(str(later)[:10])
    return (b.year - a.year) * 12 + (b.month - a.month)


def check_increase(schedule: "RentSchedule", valid_from: str, new_rent,
                   kind: str = "agreed") -> list[dict]:
    """What looks off about this increase, under §558.

    Only an ordinary increase is measured: the other kinds answer to their own
    paragraphs. Each finding carries the paragraph it rests on, so the landlord
    can check it rather than take the tool's word.
    """
    if kind != "agreed" or not schedule or not schedule.periods:
        return []
    new = _dec(new_rent)
    findings = []

    previous = schedule._at(valid_from) or schedule.periods[0]
    prev_from, prev_rent, _ = previous

    # Waiting period: fifteen months since the last increase took effect.
    if prev_from and len(schedule) > 1:
        months = _months_between(prev_from, valid_from)
        if months < WARTEFRIST_MONTHS:
            findings.append({
                "code": "wartefrist",
                "paragraph": "§558 Abs. 1 BGB",
                "message": (f"The last increase took effect on {prev_from}, "
                            f"{months} months before this one. An ordinary "
                            f"increase is owed at the earliest {WARTEFRIST_MONTHS} "
                            f"months after the previous one."),
            })

    # Kappungsgrenze: measured against the rent three years before this date.
    from datetime import date as _d
    d = _d.fromisoformat(str(valid_from)[:10])
    three_years_ago = d.replace(year=d.year - 3).isoformat()
    base = schedule.on(three_years_ago) or schedule.first()
    if base > 0:
        rise = (new - base) / base
        if rise > KAPPUNGSGRENZE_TIGHT:
            limit = (KAPPUNGSGRENZE_GENERAL if rise > KAPPUNGSGRENZE_GENERAL
                     else KAPPUNGSGRENZE_TIGHT)
            findings.append({
                "code": "kappungsgrenze",
                "paragraph": "§558 Abs. 3 BGB",
                "over_general": rise > KAPPUNGSGRENZE_GENERAL,
                "message": (
                    f"That is {rise * 100:.1f} % above the {base:.2f} € charged "
                    f"three years ago. The Kappungsgrenze allows 20 % over three "
                    f"years, and 15 % where the Land has made a "
                    f"Kappungsgrenzenverordnung — Berlin has."
                    if rise > KAPPUNGSGRENZE_GENERAL else
                    f"That is {rise * 100:.1f} % above the {base:.2f} € charged "
                    f"three years ago. Within the general 20 % Kappungsgrenze, but "
                    f"over the 15 % that applies where the Land has made a "
                    f"Kappungsgrenzenverordnung — Berlin has."),
            })

    # A reduction is lawful but is not what §558 is for, and is more often a typo.
    if new < prev_rent:
        findings.append({
            "code": "reduction",
            "paragraph": "",
            "message": (f"This is lower than the {prev_rent:.2f} € in force. "
                        f"Recorded as entered — §558 covers increases, so a "
                        f"reduction is an agreement of its own."),
        })
    return findings
