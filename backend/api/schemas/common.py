"""Field types shared by the request schemas.

Every date in this database is a TEXT column holding YYYY-MM-DD, and every
consumer — the balance sheet's string comparisons, detect_overdue's
date.fromisoformat, the tax module's _parse — trusts that shape. Nothing used
to enforce it at the door: an empty or malformed date on one contract took the
whole Payment Reminders page down with a 500, and a bad valid_from on a flat
cost silently fell out of (or into) every month's costs. These types reject
the bad value with a 422 that names the field instead.
"""
from datetime import date
from typing import Annotated

from pydantic import BeforeValidator

# The legacy string a few old rows hold for "no date" (see the
# backfill_none_string_dates migration). Treated like blank on the way in.
_BLANKS = (None, "", "None")


def _iso(v) -> str:
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    try:
        # Accept a datetime prefix ("2026-01-01T00:00") but keep only the day;
        # anything shorter than a full date is malformed.
        if len(s) < 10:
            raise ValueError
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        raise ValueError("must be a date in YYYY-MM-DD form")


def _required(v) -> str:
    if v in _BLANKS:
        raise ValueError("a date in YYYY-MM-DD form is required")
    return _iso(v)


def _optional(v) -> str | None:
    if v in _BLANKS:
        return None
    return _iso(v)


IsoDate = Annotated[str, BeforeValidator(_required)]
OptIsoDate = Annotated[str | None, BeforeValidator(_optional)]


def parse_iso_date(v) -> str | None:
    """The optional rule as a plain function, for query parameters that do
    not go through a model (e.g. POST /contracts/{id}/terminate?end_date=)."""
    return _optional(v)
