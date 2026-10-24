"""Per-flat economics: what each flat earns, costs and owes.

Everything here comes from what is already on file — rents from the running
contracts, costs from the flat's recurring charges, the mortgage split from the
same schedule the Financing page uses, and the value from the Valuation page.
Nothing is estimated except the value, and that says so.
"""
from datetime import date

from fastapi import APIRouter, Depends

import flat_economics
import tax_logic
import valuation
from auth import require_auth
from db import fetch_bundle, json_part

router = APIRouter(prefix="/insights", tags=["Insights"])

# Money travels as TEXT and is parsed back to Decimal where it is added up:
# json_build_array would hand back floats, and rent arithmetic must not go near
# binary floating point.
_PROPS_SQL = """
    SELECT id, name, we_label, COALESCE(owned, 1), market_value::text, market_value_date,
           living_sqm::text, plot_sqm::text, comparable_per_sqm::text, mea::text
    FROM properties WHERE owner_id=? ORDER BY name
"""

_CONTRACTS_SQL = """
    SELECT a.property_id, c.apartment_id, c.rent::text, c.start_date, c.end_date,
           COALESCE(c.terminated, 0), c.id
    FROM contracts c JOIN apartments a ON a.id = c.apartment_id
    WHERE c.owner_id=?
"""

# cost_type comes along so the mortgage can be told apart from the running
# costs: part of an instalment buys the flat and is not a cost at all.
_COSTS_SQL = """
    SELECT a.property_id, fc.cost_type, fc.amount::text, fc.frequency,
           fc.valid_from, fc.valid_to
    FROM flat_costs fc JOIN apartments a ON a.id = fc.apartment_id
    WHERE fc.owner_id=?
"""

_ROOMS_SQL = """
    SELECT property_id, COUNT(*) FROM apartments WHERE owner_id=? GROUP BY property_id
"""

_MORTGAGE_SQL = """
    SELECT property_id, principal::text, interest_rate_pct::text, tilgung_rate_pct::text,
           start_date, fixed_until, follow_up_rate_pct::text
    FROM mortgages WHERE owner_id=? ORDER BY start_date, id
"""

_LAND_SQL = """
    SELECT json_build_array(property_id, stichtag, brw, gfz)
    FROM (
        SELECT DISTINCT ON (property_id)
               property_id, stichtag, brw::text AS brw, gfz::text AS gfz
        FROM land_values WHERE owner_id=?
        ORDER BY property_id, stichtag DESC
    ) t
"""


def _f(v):
    return float(v) if v not in (None, "") else None


@router.get("/flats")
def flat_insights(owner: int = Depends(require_auth)):
    """Every flat's monthly economics, and the portfolio's.

    Two round trips: this bundle, and the arrears, which come from
    logic.detect_overdue so the figure here is the same one the reminders page
    acts on rather than a second implementation of the same rule.
    """
    today = date.today()
    iso = str(today)

    loaded = fetch_bundle([
        json_part("props", _PROPS_SQL, (owner,)),
        json_part("contracts", _CONTRACTS_SQL, (owner,)),
        json_part("costs", _COSTS_SQL, (owner,)),
        json_part("rooms", _ROOMS_SQL, (owner,)),
        json_part("mortgages", _MORTGAGE_SQL, (owner,)),
        ("land", _LAND_SQL, (owner,)),
    ])

    by_prop_contracts: dict = {}
    for r in loaded["contracts"]:
        by_prop_contracts.setdefault(r[0], []).append((r[1], r[2], r[3], r[4], r[5], r[6]))
    by_prop_costs: dict = {}
    for r in loaded["costs"]:
        by_prop_costs.setdefault(r[0], []).append((r[1], r[2], r[3], r[4], r[5]))
    rooms = {r[0]: r[1] for r in loaded["rooms"]}
    land = {r[0]: r for r in loaded["land"]}

    # The instalment and its interest share, per property, as of this month.
    # A loan that is paid off or not yet drawn has a zero balance and is not
    # being serviced, so it contributes nothing — the same test the Financing
    # page applies.
    inst: dict = {}
    interest: dict = {}
    debt: dict = {}
    for r in loaded["mortgages"]:
        m = {"principal": _f(r[1]), "interest_rate_pct": _f(r[2]),
             "tilgung_rate_pct": _f(r[3]), "start_date": r[4],
             "fixed_until": r[5] if r[5] and r[5] != "None" else None,
             "follow_up_rate_pct": _f(r[6])}
        try:
            b = tax_logic.year_breakdown_for(m, today.year, today.month)
            prev = (tax_logic.year_breakdown_for(m, today.year, today.month - 1)
                    if today.month > 1 else None)
        except Exception:
            continue                       # unusable terms never break the page
        if b["balance_end"] <= 0 and b["interest"] <= 0:
            continue
        pid = r[0]
        debt[pid] = debt.get(pid, 0.0) + max(b["balance_end"], 0.0)
        if b["balance_end"] > 0:
            inst[pid] = inst.get(pid, 0.0) + b["monthly_payment"]
        interest[pid] = interest.get(pid, 0.0) + round(
            b["interest"] - (prev["interest"] if prev else 0.0), 2)

    arrears = _arrears_by_property(owner)

    flats, owned_flats = [], []
    for p in loaded["props"]:
        pid, owned = p[0], bool(p[3])
        lv = land.get(pid)
        v = valuation.value_property(
            living_sqm=_f(p[6]), comparable_per_sqm=_f(p[8]),
            market_value=_f(p[4]), market_value_date=p[5],
            brw=_f(lv[2]) if lv else None, gfz=_f(lv[3]) if lv else None,
            stichtag=lv[1] if lv else None, plot_sqm=_f(p[7]), mea=_f(p[9]))

        rent, let = flat_economics.contracted_rent(by_prop_contracts.get(pid, []), iso)
        costs, mortgage_cost = flat_economics.split_costs(by_prop_costs.get(pid, []), iso)

        # The loan's own schedule where its terms are on file — it knows the
        # interest/Tilgung split. Where they are not, the flat-cost row is the
        # only record of the money and is used as the instalment, with the
        # split reported as unknown rather than guessed.
        if pid in inst:
            instalment, int_month = inst[pid], interest.get(pid, 0.0)
        elif mortgage_cost:
            instalment, int_month = float(mortgage_cost), None
        else:
            instalment, int_month = 0.0, 0.0

        e = flat_economics.economics(
            rent=rent, costs=costs,
            instalment=instalment, interest=int_month,
            # A flat that is not yours is not your asset, so it gets no yield.
            value=v["value"] if owned else None,
            debt=debt.get(pid, 0.0), rooms=rooms.get(pid, 0), let_rooms=len(let),
            arrears=arrears.get(pid, 0.0))
        entry = {
            "property_id": pid, "property_name": p[1], "we_label": p[2],
            "owned": owned, "living_sqm": _f(p[6]),
            "value": v["value"] if owned else None,
            "value_estimated": v["estimated"] if owned else None,
            "debt": round(debt.get(pid, 0.0), 2),
            "rent_per_sqm": (round(e["rent_monthly"] / _f(p[6]), 2)
                             if _f(p[6]) and e["rent_monthly"] else None),
            **e,
        }
        flats.append(entry)
        if owned:
            owned_flats.append(entry)

    return {
        "as_of": iso,
        "flats": flats,
        "summary": flat_economics.portfolio_summary(owned_flats),
        "not_owned_count": len(flats) - len(owned_flats),
    }


def _arrears_by_property(owner: int) -> dict:
    """Outstanding rent per property, from the reminders' own calculation.

    Reusing detect_overdue costs one more round trip and is worth it: a second
    implementation of the arrears rule would drift from the one the reminders
    page acts on, and then two pages would disagree about who owes what.
    """
    from logic import detect_overdue
    out: dict = {}
    try:
        rows = detect_overdue(owner=owner)
    except Exception:
        return out                          # arrears are an extra, not the page
    if not rows:
        return out
    from db import fetch
    ids = [r["contract_id"] for r in rows]
    placeholders = ",".join("?" for _ in ids)
    prop_of = dict(fetch(
        f"SELECT c.id, a.property_id FROM contracts c JOIN apartments a ON a.id=c.apartment_id "
        f"WHERE c.id IN ({placeholders}) AND c.owner_id=?", (*ids, owner)))
    for r in rows:
        pid = prop_of.get(r["contract_id"])
        if pid is not None:
            out[pid] = out.get(pid, 0.0) + float(r["amount_due"])
    return out
