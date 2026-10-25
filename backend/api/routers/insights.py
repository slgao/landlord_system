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
from rent_periods import RentSchedule, schedules_from_rows

router = APIRouter(prefix="/insights", tags=["Insights"])

# Money travels as TEXT and is parsed back to Decimal where it is added up:
# json_build_array would hand back floats, and rent arithmetic must not go near
# binary floating point.
_PROPS_SQL = """
    SELECT p.id, p.name, p.we_label, COALESCE(p.owned, 1), p.market_value::text,
           p.market_value_date, p.living_sqm::text, p.plot_sqm::text,
           p.comparable_per_sqm::text, p.mea::text,
           t.purchase_price::text, t.purchase_costs::text, t.purchase_date
    FROM properties p
    LEFT JOIN property_tax_profiles t ON t.property_id = p.id AND t.owner_id = p.owner_id
    WHERE p.owner_id=? ORDER BY p.name
"""

_CONTRACTS_SQL = """
    SELECT a.property_id, c.apartment_id, c.start_date, c.end_date,
           COALESCE(c.terminated, 0), c.id
    FROM contracts c JOIN apartments a ON a.id = c.apartment_id
    WHERE c.owner_id=?
"""

# The agreed prices of every tenancy. What a flat earns is read from the price
# in force on the day being asked about, not from one figure on the contract.
_RENTS_SQL = """
    SELECT contract_id, valid_from, rent::text, nebenkosten_vorauszahlung::text
    FROM contract_rents WHERE owner_id=? ORDER BY valid_from
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
        json_part("rents", _RENTS_SQL, (owner,)),
        json_part("costs", _COSTS_SQL, (owner,)),
        json_part("rooms", _ROOMS_SQL, (owner,)),
        json_part("mortgages", _MORTGAGE_SQL, (owner,)),
        ("land", _LAND_SQL, (owner,)),
    ])

    schedules = schedules_from_rows(loaded["rents"])
    by_prop_contracts: dict = {}
    for r in loaded["contracts"]:
        # (apartment_id, rent schedule, start, end, terminated, contract_id)
        by_prop_contracts.setdefault(r[0], []).append(
            (r[1], schedules.get(r[5], RentSchedule()), r[2], r[3], r[4], r[5]))
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
    borrowed: dict = {}
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
        # What was borrowed at the outset, whatever is left of it now: the
        # Eigenkapital a flat was bought with is the price less this.
        borrowed[pid] = borrowed.get(pid, 0.0) + (_f(r[1]) or 0.0)
        debt[pid] = debt.get(pid, 0.0) + max(b["balance_end"], 0.0)
        if b["balance_end"] > 0:
            inst[pid] = inst.get(pid, 0.0) + b["monthly_payment"]
        interest[pid] = interest.get(pid, 0.0) + round(
            b["interest"] - (prev["interest"] if prev else 0.0), 2)

    arrears = _arrears_by_property(owner)

    flats, owned_flats, sublets, warnings = [], [], [], []
    for p in loaded["props"]:
        pid, owned = p[0], bool(p[3])
        lv = land.get(pid)
        v = valuation.value_property(
            living_sqm=_f(p[6]), comparable_per_sqm=_f(p[8]),
            market_value=_f(p[4]), market_value_date=p[5],
            brw=_f(lv[2]) if lv else None, gfz=_f(lv[3]) if lv else None,
            stichtag=lv[1] if lv else None, plot_sqm=_f(p[7]), mea=_f(p[9]))

        rent, let = flat_economics.contracted_rent(by_prop_contracts.get(pid, []), iso)
        costs, mortgage_cost, to_owner = flat_economics.split_costs(
            by_prop_costs.get(pid, []), iso)

        # "Rent to the owner" is a sublet's idea. On a flat you own, such a row
        # is either a ground rent (Erbbauzins) or left over from when the flat
        # was a sublet — either way it is an ordinary running cost, and keeping
        # it in a column of its own would leave the money subtracted from the
        # cashflow but shown nowhere.
        rent_to_owner_on_owned = float(to_owner) if (owned and to_owner) else 0.0
        if owned and to_owner:
            costs += to_owner
            to_owner = 0

        # The loan's own schedule where its terms are on file — it knows the
        # interest/Tilgung split. Where they are not, the flat-cost row is the
        # only record of the money and is used as the instalment, with the
        # split reported as unknown rather than guessed.
        instalment, split_known = flat_economics.resolve_instalment(
            inst.get(pid), mortgage_cost)
        int_month = interest.get(pid, 0.0) if split_known and instalment else (
            0.0 if not instalment else None)

        # Both records of the mortgage on file and disagreeing: the loans are
        # used, but the typed figure is reported so the drift cannot hide.
        clash = flat_economics.mortgage_conflict(inst.get(pid), mortgage_cost)
        if clash:
            warnings.append({"kind": "mortgage_conflict", "property_id": pid,
                             "property_name": p[1], **clash})
        if rent_to_owner_on_owned:
            warnings.append({"kind": "rent_to_owner_on_owned", "property_id": pid,
                             "property_name": p[1], "amount": round(rent_to_owner_on_owned, 2)})
        if not owned and instalment:
            warnings.append({"kind": "loan_on_sublet", "property_id": pid,
                             "property_name": p[1], "amount": round(instalment, 2)})

        e = flat_economics.economics(
            rent=rent, costs=costs,
            instalment=instalment, interest=int_month,
            # A flat that is not yours is not your asset, so it gets no yield.
            value=v["value"] if owned else None,
            debt=debt.get(pid, 0.0), rooms=rooms.get(pid, 0), let_rooms=len(let),
            arrears=arrears.get(pid, 0.0), rent_to_owner=float(to_owner))
        bought = flat_economics.purchase_equity(
            _f(p[10]), _f(p[11]), borrowed.get(pid)) if owned else None
        entry = {
            "property_id": pid, "property_name": p[1], "we_label": p[2],
            "owned": owned, "living_sqm": _f(p[6]),
            "purchase_date": p[12] if p[12] and p[12] != "None" else None,
            **({"purchase": bought,
                "equity_return_invested": flat_economics.equity_return_on_investment(
                    e["operating_monthly"], bought["equity_invested"]),
                "cash_return_invested": flat_economics.equity_return_on_investment(
                    e["cashflow_monthly"], bought["equity_invested"]),
                "value_gain": flat_economics.value_gain(
                    v["value"], bought["purchase_price"])}
               if bought else {"purchase": None, "equity_return_invested": None,
                               "cash_return_invested": None, "value_gain": None}),
            "value": v["value"] if owned else None,
            "value_estimated": v["estimated"] if owned else None,
            "debt": round(debt.get(pid, 0.0), 2),
            "rent_per_sqm": (round(e["rent_monthly"] / _f(p[6]), 2)
                             if _f(p[6]) and e["rent_monthly"] else None),
            **e,
        }
        flats.append(entry)
        (owned_flats if owned else sublets).append(entry)

    return {
        "as_of": iso,
        "flats": flats,
        "summary": flat_economics.portfolio_summary(owned_flats),
        "purchase": flat_economics.portfolio_purchase(owned_flats),
        "sublets": flat_economics.sublet_summary(sublets),
        # Contradictions in the data worth a landlord's attention: a mortgage
        # recorded twice and disagreeing, a flat you own paying rent to an
        # owner, a flat you do not own carrying a loan.
        "warnings": warnings,
        "not_owned_count": len(sublets),
    }


def _arrears_by_property(owner: int) -> dict:
    """Outstanding rent per property, from the reminders' own calculation.

    Reusing detect_overdue rather than reimplementing the arrears rule: a
    second implementation would drift from the one the reminders page acts on,
    and then two pages would disagree about who owes what. It used to cost a
    further round trip to map each contract to its flat; detect_overdue's own
    query already joins the flat, so it answers that too now.
    """
    from logic import detect_overdue
    out: dict = {}
    try:
        rows = detect_overdue(owner=owner)
    except Exception:
        return out                          # arrears are an extra, not the page
    for r in rows:
        pid = r.get("property_id")
        if pid is not None:
            out[pid] = out.get(pid, 0.0) + float(r.get("amount_due") or 0)
    return out


