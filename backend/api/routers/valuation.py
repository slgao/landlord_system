"""What the portfolio is worth, and the open data behind it.

The land value comes from Berlin's Geoportal on demand and is then kept with
its Stichtag (see land_value.py), so a page load never waits on an external
service and a stored figure is always traceable to the day it was official.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import land_value
import tax_logic
import valuation
from auth import require_auth
from db import execute_returning, fetch, fetch_bundle, json_part

router = APIRouter(prefix="/valuation", tags=["Valuation"])

# The Bodenrichtwertkarte for a year is published the following March, so
# asking for the current year before then finds nothing. The fetch walks back
# from the newest plausible Stichtag until a zone answers.
_MAX_YEARS_BACK = 3


class LandValueOut(BaseModel):
    stichtag: str
    brw: float
    gfz: float | None = None
    nutzung: str | None = None
    bezirk: str | None = None
    ortsteil: str | None = None
    zone_id: str | None = None
    matched_address: str | None = None
    source: str | None = None
    fetched_at: str | None = None
    # More than one address matched the register, so the pick is a guess.
    ambiguous: bool = False


def _own_property(property_id: int, owner: int):
    rows = fetch("SELECT address FROM properties WHERE id=? AND owner_id=?",
                 (property_id, owner))
    if not rows:
        raise HTTPException(404, "Property not found")
    return rows[0][0]


@router.post("/properties/{property_id}/land-value", response_model=LandValueOut)
def refresh_land_value(property_id: int, owner: int = Depends(require_auth)):
    """Look this property's land value up in Berlin's open data and store it.

    On demand, never on a page load: it is two requests to an external service,
    and the answer only changes once a year.
    """
    address = _own_property(property_id, owner)
    if not address:
        raise HTTPException(422, "This property has no address to look up. "
                                "Add one like 'Weichselstr.57, 12045 Berlin'.")

    year = date.today().year
    last_error = None
    found = None
    for attempt in range(_MAX_YEARS_BACK):
        try:
            found = land_value.lookup(address, year - attempt)
            break
        except land_value.LookupError_ as e:
            last_error = e
        except Exception as e:                      # network, service, bad payload
            raise HTTPException(
                502, "Berlin's land-value service could not be reached (%s). "
                     "It is an external service — try again shortly."
                     % type(e).__name__) from e
    if not found:
        raise HTTPException(404, str(last_error))

    # One row per Stichtag: a new year adds to the series rather than
    # overwriting it, so the land value's own history stays visible.
    execute_returning("""
        INSERT INTO land_values
          (property_id, stichtag, brw, gfz, nutzung, beitragszustand, bezirk, ortsteil,
           zone_id, east, north, matched_address, source, fetched_at, owner_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT (property_id, stichtag) DO UPDATE SET
          brw=EXCLUDED.brw, gfz=EXCLUDED.gfz, nutzung=EXCLUDED.nutzung,
          beitragszustand=EXCLUDED.beitragszustand, bezirk=EXCLUDED.bezirk,
          ortsteil=EXCLUDED.ortsteil, zone_id=EXCLUDED.zone_id,
          east=EXCLUDED.east, north=EXCLUDED.north,
          matched_address=EXCLUDED.matched_address, source=EXCLUDED.source,
          fetched_at=EXCLUDED.fetched_at
        RETURNING id
    """, (property_id, found["stichtag"], found["brw"], found["gfz"], found["nutzung"],
          found["beitragszustand"], found["bezirk"], found["ortsteil"], found["zone_id"],
          found["east"], found["north"], found["matched_address"], found["source"],
          str(date.today()), owner))

    return LandValueOut(fetched_at=str(date.today()), ambiguous=found["ambiguous"],
                        **{k: found[k] for k in
                           ("stichtag", "brw", "gfz", "nutzung", "bezirk", "ortsteil",
                            "zone_id", "matched_address", "source")})


@router.get("/properties/{property_id}/land-values", response_model=list[LandValueOut])
def land_value_history(property_id: int, owner: int = Depends(require_auth)):
    """Every Stichtag on file for this property, newest first."""
    _own_property(property_id, owner)
    rows = fetch("""
        SELECT stichtag, brw, gfz, nutzung, bezirk, ortsteil, zone_id,
               matched_address, source, fetched_at
        FROM land_values WHERE property_id=? AND owner_id=? ORDER BY stichtag DESC
    """, (property_id, owner))
    return [LandValueOut(
        stichtag=r[0], brw=float(r[1]), gfz=float(r[2]) if r[2] is not None else None,
        nutzung=r[3], bezirk=r[4], ortsteil=r[5], zone_id=r[6],
        matched_address=r[7], source=r[8], fetched_at=r[9]) for r in rows]


# The newest Stichtag per property, and the row that belongs to it. DISTINCT ON
# does both in one pass, but it cannot sit in a column list — so the json wrap
# goes outside it and this part is written out rather than built by json_part().
_LATEST_LAND_SQL = """
    SELECT json_build_array(property_id, stichtag, brw, gfz, nutzung, bezirk, ortsteil,
                            zone_id, matched_address, fetched_at)
    FROM (
        SELECT DISTINCT ON (property_id)
               property_id, stichtag, brw::text AS brw, gfz::text AS gfz, nutzung,
               bezirk, ortsteil, zone_id, matched_address, fetched_at
        FROM land_values WHERE owner_id=?
        ORDER BY property_id, stichtag DESC
    ) t
"""

_PROPS_SQL = """
    SELECT id, name, address, we_label, mea::text, market_value::text, market_value_date,
           living_sqm::text, plot_sqm::text, comparable_per_sqm::text, valuation_note
    FROM properties WHERE owner_id=? ORDER BY name
"""

_MORTGAGE_SQL = """
    SELECT id, property_id, label, principal::text, interest_rate_pct::text,
           tilgung_rate_pct::text, start_date, note, fixed_until, follow_up_rate_pct::text
    FROM mortgages WHERE owner_id=? ORDER BY start_date, id
"""


def _f(v):
    return float(v) if v not in (None, "") else None


@router.get("/overview")
def overview(owner: int = Depends(require_auth)):
    """Every property's value, the debt against it, and the equity left.

    One round trip. Nothing here reaches out to Berlin — the land values are
    whatever was last fetched, each carrying the Stichtag it was official on.
    """
    today = date.today()
    loaded = fetch_bundle([
        json_part("props", _PROPS_SQL, (owner,)),
        ("land", _LATEST_LAND_SQL, (owner,)),
        json_part("mortgages", _MORTGAGE_SQL, (owner,)),
    ])

    land = {r[0]: r for r in loaded["land"]}

    # Debt per property: what is actually still owed today, by the same
    # schedule the Financing page uses. A loan signed but not yet drawn, or one
    # already paid off, has a balance of zero and contributes nothing.
    debt: dict[int, float] = {}
    for r in loaded["mortgages"]:
        m = {"principal": _f(r[3]), "interest_rate_pct": _f(r[4]),
             "tilgung_rate_pct": _f(r[5]), "start_date": r[6],
             "fixed_until": r[8] if r[8] and r[8] != "None" else None,
             "follow_up_rate_pct": _f(r[9])}
        try:
            bal = tax_logic.year_breakdown_for(m, today.year, today.month)["balance_end"]
        except Exception:
            continue                       # unusable terms never break the page
        debt[r[1]] = debt.get(r[1], 0.0) + max(bal, 0.0)

    out, valued = [], []
    for p in loaded["props"]:
        pid = p[0]
        lv = land.get(pid)
        v = valuation.value_property(
            living_sqm=_f(p[7]), comparable_per_sqm=_f(p[9]),
            market_value=_f(p[5]), market_value_date=p[6],
            brw=_f(lv[2]) if lv else None, gfz=_f(lv[3]) if lv else None,
            stichtag=lv[1] if lv else None,
            plot_sqm=_f(p[8]), mea=_f(p[4]))
        d = debt.get(pid, 0.0)
        entry = {
            "property_id": pid, "property_name": p[1], "address": p[2],
            "we_label": p[3], "living_sqm": _f(p[7]), "plot_sqm": _f(p[8]),
            "comparable_per_sqm": _f(p[9]), "valuation_note": p[10],
            "debt": round(d, 2),
            "equity": round(v["value"] - d, 2) if v["value"] is not None else None,
            "ltv": (round(d / v["value"] * 100, 1)
                    if v["value"] else None),
            "bezirk": lv[5] if lv else None, "ortsteil": lv[6] if lv else None,
            "land_fetched_at": lv[9] if lv else None,
            "matched_address": lv[8] if lv else None,
            **v,
        }
        out.append(entry)
        valued.append(v)

    return {
        "as_of": str(today),
        "properties": out,
        "totals": valuation.portfolio_totals(valued, [debt.get(p[0], 0.0)
                                                      for p in loaded["props"]]),
        "licence": land_value.LICENCE,
    }
