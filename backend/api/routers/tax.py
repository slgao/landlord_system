"""Anlage-V helper endpoints (docs/PRD-tax-module.md).

Report philosophy: every euro in the output is traceable — each block carries
its source rows ("derivation"), and figures the DB can't know (gap-year income,
Sondertilgung-affected interest) are overridable per (property, year, field)
via tax_year_overrides. Manual always wins over computed.
"""
import json
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool
from typing import Literal, Optional

from db import fetch, fetch_bundle, execute, execute_returning, insert
from auth import require_auth
from api.schemas.common import IsoDate, OptIsoDate
import tax_logic

from kaution_rules import NK_CATEGORY, NK_REF_TYPE, RENT_CATEGORIES

router = APIRouter(prefix="/tax", tags=["Tax"])

# A tax year outside this range is a typo; the date arithmetic would throw.
_Year = Query(ge=1900, le=2200)

# Which recurring flat_costs count as Werbungskosten by default.
# "Miete" is the landlord's own rent cost type (not a letting expense);
# "Mortgage" mixes Tilgung into the amount — interest is handled via the
# mortgages table / Schuldzinsen instead, so it must not be summed here.
NON_DEDUCTIBLE_COST_TYPES = {"Miete", "Mortgage"}

EXPENSE_CATEGORIES = [
    "Erhaltungsaufwand", "Renovierung", "Instandhaltung",
    "Schuldzinsen", "Geldbeschaffungskosten",
    "Grundsteuer", "Versicherung", "Verwaltung", "Hausgeld",
    "Versorgerabrechnung", "Fahrtkosten", "Sonstige",
]

# What a provider bill bills. Setting one on an expense makes it a bill that
# tenant Nebenkostenabrechnungen can be linked to (see nk_settlements).
UTILITIES = ("strom", "gas", "wasser", "heizung", "betriebskosten", "muell", "sonstige")
Utility = Literal["strom", "gas", "wasser", "heizung", "betriebskosten", "muell", "sonstige"]

_MAX_PDF_BYTES = 5 * 1024 * 1024


# ── Schemas ──────────────────────────────────────────────────────────────────

class TaxProfileIn(BaseModel):
    purchase_date: OptIsoDate = None
    purchase_price: Optional[float] = None
    building_share_pct: Optional[float] = None
    afa_rate_pct: Optional[float] = None
    notes: Optional[str] = None


class MortgageIn(BaseModel):
    property_id: int
    label: Optional[str] = None
    principal: float = Field(gt=0)
    interest_rate_pct: float = Field(ge=0, le=25)
    tilgung_rate_pct: float = Field(ge=0, le=100)
    start_date: IsoDate
    # End of the Zinsbindung, and the rate to assume after it. Without these a
    # 2018 loan at 1.44 % was projected at 1.44 % out to 2045 — a rate that
    # expires in 2028. Left empty, the current rate simply runs on, as before.
    fixed_until: OptIsoDate = None
    follow_up_rate_pct: Optional[float] = Field(default=None, ge=0, le=25)
    note: Optional[str] = None


class ExpenseIn(BaseModel):
    property_id: int
    apartment_id: Optional[int] = None
    expense_date: IsoDate
    amount: float
    category: str
    vendor: Optional[str] = None
    note: Optional[str] = None
    deductible: int = 1
    distribute_years: int = 1
    source_file: Optional[str] = None  # scanned receipt this row came from
    # Provider bill: only written when sent, so the Tax Setup form, which
    # does not know about them, cannot wipe them by saving an edit.
    utility: Optional[Utility] = None
    period_start: OptIsoDate = None
    period_end: OptIsoDate = None
    bill_total: Optional[float] = None    # Gesamtkosten of the period, per the bill

    @model_validator(mode="after")
    def _bill(self):
        if self.utility and not (self.period_start and self.period_end):
            raise ValueError("a provider bill needs its billing period")
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end must not be before period_start")
        return self


_BILL_FIELDS = ("utility", "period_start", "period_end", "bill_total")


class NkSplitIn(BaseModel):
    nebenkosten_vorauszahlung: Optional[float] = None  # None clears
    # Omitted: left as it is. See api/schemas/contract.NkMode.
    nk_mode: Optional[Literal["prepayment", "flat"]] = None


class OverrideIn(BaseModel):
    field: str
    value: Optional[float] = None  # None deletes the override
    note: Optional[str] = None


class RelevanceIn(BaseModel):
    tax_relevant: bool


# Every computed/derived figure in the report can be manually overridden per
# (property, year). Manual always wins; the computed value stays visible.
OVERRIDE_FIELDS = {
    "income_total",      # total income (payments sum or contract estimate)
    "income_kaltmiete",  # Kaltmiete line; Umlagen derive as total - Kaltmiete
    "afa",               # building depreciation
    "schuldzinsen",      # mortgage interest
    "recurring_total",   # sum of recurring flat costs
}


def _clean(v):
    return None if v is None or v == "None" else v


# ── Profiles + mortgages ─────────────────────────────────────────────────────

# Every mortgage read goes through this list, so no call site can forget the
# Zinsbindung columns and quietly project the fixed rate to payoff.
_MORTGAGE_COLS = ("id, property_id, label, principal, interest_rate_pct, "
                  "tilgung_rate_pct, start_date, note, fixed_until, follow_up_rate_pct")


def _mortgage_row(r) -> dict:
    fixed_until = _clean(r[8])
    rate_after, assumed = tax_logic.follow_up_rate(float(r[4]), fixed_until,
                                                   r[9] if r[9] is not None else None)
    return {
        "id": r[0], "property_id": r[1], "label": _clean(r[2]),
        "principal": float(r[3]), "interest_rate_pct": float(r[4]),
        "tilgung_rate_pct": float(r[5]), "start_date": r[6], "note": _clean(r[7]),
        "fixed_until": fixed_until,
        # What the projection actually used, and whether the loan supplied it.
        "follow_up_rate_pct": rate_after,
        "follow_up_assumed": assumed,
    }


@router.get("/profiles")
def list_profiles(owner: int = Depends(require_auth)):
    props = fetch("SELECT id, name, COALESCE(tax_relevant,1) FROM properties "
                  "WHERE owner_id=? ORDER BY name", (owner,))
    profiles = {r[0]: r for r in fetch(
        "SELECT property_id, purchase_date, purchase_price, building_share_pct,"
        "       afa_rate_pct, notes FROM property_tax_profiles WHERE owner_id=?", (owner,))}
    mortgages: dict[int, list] = {}
    for r in fetch(f"SELECT {_MORTGAGE_COLS} FROM mortgages "
                   "WHERE owner_id=? ORDER BY id", (owner,)):
        mortgages.setdefault(r[1], []).append(_mortgage_row(r))

    out = []
    for pid, name, relevant in props:
        p = profiles.get(pid)
        entry = {
            "property_id": pid, "property_name": name,
            "tax_relevant": bool(relevant),
            "purchase_date": _clean(p[1]) if p else None,
            "purchase_price": float(p[2]) if p and p[2] is not None else None,
            "building_share_pct": float(p[3]) if p and p[3] is not None else None,
            "afa_rate_pct": float(p[4]) if p and p[4] is not None else None,
            "notes": _clean(p[5]) if p else None,
            "mortgages": mortgages.get(pid, []),
            "afa_annual": None,
        }
        if p and all(v is not None for v in (entry["purchase_date"], entry["purchase_price"],
                                             entry["building_share_pct"], entry["afa_rate_pct"])):
            entry["afa_annual"] = tax_logic.afa_for_year(
                entry["purchase_price"], entry["building_share_pct"],
                entry["afa_rate_pct"], entry["purchase_date"],
                # a full (non-first, non-final) year shows the plain annual figure
                tax_logic._parse(entry["purchase_date"]).year + 1,
            )["annual"]
        out.append(entry)
    return out


@router.put("/profiles/{property_id}")
def upsert_profile(property_id: int, body: TaxProfileIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    vals = (body.purchase_date, body.purchase_price, body.building_share_pct,
            body.afa_rate_pct, body.notes)
    if fetch("SELECT id FROM property_tax_profiles WHERE property_id=? AND owner_id=?",
             (property_id, owner)):
        execute("""UPDATE property_tax_profiles SET purchase_date=?, purchase_price=?,
                   building_share_pct=?, afa_rate_pct=?, notes=? WHERE property_id=? AND owner_id=?""",
                (*vals, property_id, owner))
    else:
        insert("property_tax_profiles", (property_id, *vals))
    return {"property_id": property_id, **body.model_dump()}


@router.put("/properties/{property_id}/relevance")
def set_tax_relevance(property_id: int, body: RelevanceIn, owner: int = Depends(require_auth)):
    """Include/exclude a property from the tax report (e.g. managed for
    someone else). Separate from the profile upsert so a toggle can never
    clobber purchase data."""
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    execute("UPDATE properties SET tax_relevant=? WHERE id=? AND owner_id=?",
            (1 if body.tax_relevant else 0, property_id, owner))
    return {"property_id": property_id, "tax_relevant": body.tax_relevant}


@router.post("/mortgages", status_code=201)
def create_mortgage(body: MortgageIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (body.property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    new_id = execute_returning(
        "INSERT INTO mortgages (property_id, label, principal, interest_rate_pct, "
        "tilgung_rate_pct, start_date, note, fixed_until, follow_up_rate_pct, owner_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id",
        (body.property_id, body.label, body.principal, body.interest_rate_pct,
         body.tilgung_rate_pct, body.start_date, body.note, body.fixed_until,
         body.follow_up_rate_pct, owner))[0][0]
    r = fetch(f"SELECT {_MORTGAGE_COLS} FROM mortgages WHERE id=?", (new_id,))[0]
    return _mortgage_row(r)


@router.put("/mortgages/{mortgage_id}")
def update_mortgage(mortgage_id: int, body: MortgageIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM mortgages WHERE id=? AND owner_id=?", (mortgage_id, owner)):
        raise HTTPException(status_code=404, detail="Mortgage not found")
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (body.property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    execute("""UPDATE mortgages SET property_id=?, label=?, principal=?, interest_rate_pct=?,
               tilgung_rate_pct=?, start_date=?, note=?, fixed_until=?, follow_up_rate_pct=?
               WHERE id=? AND owner_id=?""",
            (body.property_id, body.label, body.principal, body.interest_rate_pct,
             body.tilgung_rate_pct, body.start_date, body.note, body.fixed_until,
             body.follow_up_rate_pct, mortgage_id, owner))
    r = fetch(f"SELECT {_MORTGAGE_COLS} FROM mortgages WHERE id=?", (mortgage_id,))[0]
    return _mortgage_row(r)


@router.delete("/mortgages/{mortgage_id}", status_code=204)
def delete_mortgage(mortgage_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM mortgages WHERE id=? AND owner_id=?", (mortgage_id, owner)):
        raise HTTPException(status_code=404, detail="Mortgage not found")
    execute("DELETE FROM mortgages WHERE id=? AND owner_id=?", (mortgage_id, owner))


# ── Amortisation (Zins/Tilgung development) ──────────────────────────────────

def _merge_schedules(schedules: list[list[dict]]) -> list[dict]:
    """Sum several loan schedules onto one calendar-year timeline.

    Loans on the same property rarely start together (a KfW tranche typically
    lands a year after the main loan) and never finish together, so the merged
    range spans the earliest start to the latest payoff. Outside a loan's own
    life it contributes nothing to that year's interest/Tilgung and nothing to
    the outstanding debt — but its cumulative totals must *persist* after payoff,
    or the portfolio's "interest paid so far" would drop back to zero the year a
    loan ends.
    """
    if not schedules:
        return []
    years = sorted({r["year"] for s in schedules for r in s})
    out = []
    for y in years:
        acc = {"year": y, "interest": 0.0, "tilgung": 0.0, "payment": 0.0,
               "balance_end": 0.0, "interest_cum": 0.0, "tilgung_cum": 0.0}
        for sched in schedules:
            row = next((r for r in sched if r["year"] == y), None)
            if row is not None:
                for k in ("interest", "tilgung", "payment", "balance_end",
                          "interest_cum", "tilgung_cum"):
                    acc[k] += row[k]
            elif y > sched[-1]["year"]:      # paid off — carry the totals forward
                acc["interest_cum"] += sched[-1]["interest_cum"]
                acc["tilgung_cum"] += sched[-1]["tilgung_cum"]
            # y < sched[0]["year"] — the loan does not exist yet, contributes 0
        out.append({k: (v if k == "year" else round(v, 2)) for k, v in acc.items()})
    return out


def _as_of(m: dict, year: int, month: int) -> dict:
    """What has actually been paid on this loan through `month` of `year`.

    Same convention as the balance sheet's _financing: the current year stops at
    the current month, so these are figures to date, not a projected year-end.
    """
    b = tax_logic.year_breakdown_for(m, year, month)
    # `month` alone: the year so far, less the year up to the month before it.
    # January has no month before it, so the year so far is already the month.
    prev = tax_logic.year_breakdown_for(m, year, month - 1) if month > 1 else None
    return {"balance_now": b["balance_end"], "interest_since_start": b["interest_total"],
            "tilgung_since_start": b["equity_total"], "monthly_payment": b["monthly_payment"],
            "interest_month": round(b["interest"] - (prev["interest"] if prev else 0.0), 2),
            "tilgung_month": round(b["tilgung"] - (prev["tilgung"] if prev else 0.0), 2)}


@router.get("/amortization")
def amortization(owner: int = Depends(require_auth)):
    """Zins/Tilgung development over the whole life of every loan.

    One entry per property that actually carries a mortgage — properties without
    one are omitted rather than returned empty, so the page has nothing to filter.
    Each loan carries its full year-by-year schedule (past *and* projected), and
    the property's `combined` timeline sums them.
    """
    today = date.today()
    mortgages: dict[int, list] = {}
    for r in fetch(f"SELECT {_MORTGAGE_COLS} FROM mortgages "
                   "WHERE owner_id=? ORDER BY start_date, id", (owner,)):
        mortgages.setdefault(r[1], []).append(_mortgage_row(r))
    if not mortgages:
        return {"as_of": str(today), "properties": [], "totals": None}

    # Market value is what turns a debt figure into an equity figure.
    names, values = {}, {}
    for pid, name, mv, mvd in fetch(
            "SELECT id, name, market_value, market_value_date FROM properties "
            "WHERE owner_id=?", (owner,)):
        names[pid] = name
        values[pid] = (float(mv) if mv is not None else None,
                       mvd if mvd and mvd != "None" else None)
    flats: dict[int, list] = {}
    for pid, label in fetch("SELECT property_id, name FROM apartments WHERE owner_id=? "
                            "ORDER BY name", (owner,)):
        flats.setdefault(pid, []).append(label)

    props, all_scheds = [], []
    for pid, loans in mortgages.items():
        entries = []
        for m in loans:
            sched = tax_logic.schedule_for(m)
            if not sched:                     # unusable terms — skip, never crash the page
                continue
            # What is still owed when the fixed rate ends — the sum that has to
            # be refinanced at whatever the market then offers.
            reset = tax_logic._parse(m["fixed_until"])
            bal_at_reset = (tax_logic.year_breakdown_for(m, reset.year, reset.month)["balance_end"]
                            if reset else None)
            entries.append({**m, "schedule": sched,
                            "paid_off_year": sched[-1]["year"],
                            "interest_lifetime": sched[-1]["interest_cum"],
                            "balance_at_reset": bal_at_reset,
                            **_as_of(m, today.year, today.month)})
        if not entries:
            continue
        scheds = [e["schedule"] for e in entries]
        all_scheds += scheds
        # What you actually pay each month is the rate on the loans being
        # serviced *now*. A loan that is paid off — or signed but not yet drawn —
        # still has a contractual rate (the loan table shows it), but summing it
        # into the property's rate would invoice you for a loan you no longer
        # have. balance_now is 0 in both of those cases, which is exactly the test.
        rate_now = sum(e["monthly_payment"] for e in entries if e["balance_now"] > 0)
        market_value, value_date = values.get(pid, (None, None))
        balance_now = round(sum(e["balance_now"] for e in entries), 2)
        props.append({
            "property_id": pid,
            "property_name": names.get(pid, f"Property #{pid}"),
            "apartments": flats.get(pid, []),
            # Equity only means anything once a value is on file; None says
            # "not known" rather than quietly implying the debt is the whole story.
            "market_value": market_value,
            "market_value_date": value_date,
            "equity": round(market_value - balance_now, 2) if market_value is not None else None,
            # The nearest reset across this property's loans — what the projection
            # below stops being a fact at.
            "next_reset": min((e["fixed_until"] for e in entries if e["fixed_until"]), default=None),
            "mortgages": entries,
            "combined": _merge_schedules(scheds),
            "principal_total": round(sum(e["principal"] for e in entries), 2),
            "balance_now": round(sum(e["balance_now"] for e in entries), 2),
            "interest_since_start": round(sum(e["interest_since_start"] for e in entries), 2),
            "tilgung_since_start": round(sum(e["tilgung_since_start"] for e in entries), 2),
            "interest_month": round(sum(e["interest_month"] for e in entries), 2),
            "tilgung_month": round(sum(e["tilgung_month"] for e in entries), 2),
            "interest_lifetime": round(sum(e["interest_lifetime"] for e in entries), 2),
            "monthly_payment": round(rate_now, 2),
            "paid_off_year": max(e["paid_off_year"] for e in entries),
        })

    props.sort(key=lambda p: p["property_name"])
    # Portfolio equity is only honest when every financed property has a value;
    # summing the ones that do would understate it and look like a real number.
    valued = [p for p in props if p["market_value"] is not None]
    all_valued = bool(valued) and len(valued) == len(props)
    totals = {
        # Both are withheld until every financed property has a value. A partial
        # sum is worse than nothing here: it would pit some of the value against
        # all of the debt and report an equity far below the truth.
        "market_value": round(sum(p["market_value"] for p in valued), 2) if all_valued else None,
        "equity": round(sum(p["equity"] for p in valued), 2) if all_valued else None,
        "properties_valued": len(valued),
        "properties_total": len(props),
        "next_reset": min((p["next_reset"] for p in props if p["next_reset"]), default=None),
        "principal_total": round(sum(p["principal_total"] for p in props), 2),
        "balance_now": round(sum(p["balance_now"] for p in props), 2),
        "interest_since_start": round(sum(p["interest_since_start"] for p in props), 2),
        "tilgung_since_start": round(sum(p["tilgung_since_start"] for p in props), 2),
        "interest_month": round(sum(p["interest_month"] for p in props), 2),
        "tilgung_month": round(sum(p["tilgung_month"] for p in props), 2),
        "interest_lifetime": round(sum(p["interest_lifetime"] for p in props), 2),
        "monthly_payment": round(sum(p["monthly_payment"] for p in props), 2),
        "paid_off_year": max((p["paid_off_year"] for p in props), default=None),
        "combined": _merge_schedules(all_scheds),
    }
    return {"as_of": str(today), "properties": props, "totals": totals}


# ── Expenses ─────────────────────────────────────────────────────────────────

_EXPENSE_SELECT = """
    SELECT e.id, e.property_id, p.name, e.apartment_id, e.expense_date, e.amount,
           e.category, e.vendor, e.note, e.deductible, e.distribute_years, e.source_file,
           e.utility, e.period_start, e.period_end, e.bill_total,
           COALESCE(e.tenant_settled, 0), e.pdf IS NOT NULL
    FROM expenses e JOIN properties p ON p.id = e.property_id
"""


def _expense_row(r) -> dict:
    return {
        "id": r[0], "property_id": r[1], "property_name": r[2],
        "apartment_id": r[3], "expense_date": r[4], "amount": float(r[5]),
        "category": r[6], "vendor": _clean(r[7]), "note": _clean(r[8]),
        "deductible": int(r[9] or 0), "distribute_years": int(r[10] or 1),
        "source_file": _clean(r[11]),
        "utility": r[12], "period_start": _clean(r[13]), "period_end": _clean(r[14]),
        "bill_total": float(r[15]) if r[15] is not None else None,
        "tenant_settled": bool(r[16]), "has_pdf": bool(r[17]),
    }


@router.get("/expenses")
def list_expenses(year: int | None = None, property_id: int | None = None,
                  owner: int = Depends(require_auth)):
    rows = [_expense_row(r) for r in fetch(
        f"{_EXPENSE_SELECT} WHERE e.owner_id=? ORDER BY e.expense_date DESC", (owner,))]
    if property_id:
        rows = [r for r in rows if r["property_id"] == property_id]
    if year:
        # Include rows whose §82b spreading window touches the year. Use != 0,
        # not > 0: a credit note (Gutschrift) is a negative amount and its share
        # is negative in the affected year — > 0 silently dropped it from the
        # report/PDF, overstating costs. Rows outside the window return 0.0 and
        # are correctly excluded.
        #
        # `share_this_year` comes along so a caller filtering by year can show
        # what the row actually contributes to it: a repair spread over three
        # years is listed under each of them, and its full amount is not what
        # lands in any one of them.
        out = []
        for r in rows:
            share = tax_logic.expense_share_for_year(
                r["expense_date"], r["amount"], r["distribute_years"], year)
            if share != 0:
                out.append({**r, "share_this_year": share})
        return out
    return rows


@router.post("/expenses", status_code=201)
def create_expense(body: ExpenseIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (body.property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    # Named columns: the bill columns sit after owner_id, so the positional
    # db.insert() would put values in the wrong places.
    new_id = execute_returning("""
        INSERT INTO expenses (property_id, apartment_id, expense_date, amount, category,
                              vendor, note, deductible, distribute_years, source_file,
                              utility, period_start, period_end, bill_total, owner_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id
    """, (body.property_id, body.apartment_id, body.expense_date, body.amount,
          body.category, body.vendor, body.note, body.deductible, body.distribute_years,
          body.source_file, body.utility, body.period_start, body.period_end,
          body.bill_total, owner))[0][0]
    r = fetch(f"{_EXPENSE_SELECT} WHERE e.id=?", (new_id,))[0]
    return _expense_row(r)


@router.put("/expenses/{expense_id}")
def update_expense(expense_id: int, body: ExpenseIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM expenses WHERE id=? AND owner_id=?", (expense_id, owner)):
        raise HTTPException(status_code=404, detail="Expense not found")
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (body.property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    execute("""UPDATE expenses SET property_id=?, apartment_id=?, expense_date=?, amount=?,
               category=?, vendor=?, note=?, deductible=?, distribute_years=?, source_file=?
               WHERE id=? AND owner_id=?""",
            (body.property_id, body.apartment_id, body.expense_date, body.amount,
             body.category, body.vendor, body.note, body.deductible,
             body.distribute_years, body.source_file, expense_id, owner))
    sent = [f for f in _BILL_FIELDS if f in body.model_fields_set]
    if sent:
        execute(f"UPDATE expenses SET {', '.join(f + '=?' for f in sent)} "
                "WHERE id=? AND owner_id=?",
                (*(getattr(body, f) for f in sent), expense_id, owner))
    r = fetch(f"{_EXPENSE_SELECT} WHERE e.id=?", (expense_id,))[0]
    return _expense_row(r)


@router.put("/expenses/{expense_id:int}/pdf")
async def upload_expense_pdf(expense_id: int, file: UploadFile = File(...),
                             owner: int = Depends(require_auth)):
    """The bill itself, kept in the database next to the row."""
    data = await file.read(_MAX_PDF_BYTES + 1)
    if len(data) > _MAX_PDF_BYTES:
        raise HTTPException(413, "The PDF is larger than 5 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "That file is not a PDF")

    def _store():
        if not fetch("SELECT id FROM expenses WHERE id=? AND owner_id=?", (expense_id, owner)):
            raise HTTPException(404, "Expense not found")
        execute("UPDATE expenses SET pdf=? WHERE id=? AND owner_id=?", (data, expense_id, owner))
        return _expense_row(fetch(f"{_EXPENSE_SELECT} WHERE e.id=?", (expense_id,))[0])
    return await run_in_threadpool(_store)


# :int — otherwise "/expenses/inventory/pdf" (the Belegliste) would match here.
@router.get("/expenses/{expense_id:int}/pdf")
def download_expense_pdf(expense_id: int, owner: int = Depends(require_auth)):
    rows = fetch("SELECT pdf, expense_date FROM expenses WHERE id=? AND owner_id=?",
                 (expense_id, owner))
    if not rows or rows[0][0] is None:
        raise HTTPException(404, "No PDF stored for this expense")
    return Response(content=bytes(rows[0][0]), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="Rechnung_{rows[0][1]}.pdf"'})


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM expenses WHERE id=? AND owner_id=?", (expense_id, owner)):
        raise HTTPException(status_code=404, detail="Expense not found")
    execute("DELETE FROM expenses WHERE id=? AND owner_id=?", (expense_id, owner))


@router.get("/expense-categories")
def expense_categories():
    return EXPENSE_CATEGORIES


@router.get("/expenses/inventory/pdf")
def expense_inventory_pdf(year: int = _Year, property_id: int | None = None,
                          owner: int = Depends(require_auth)):
    """Belegliste: all bills PAID in `year` (by expense_date, full amounts —
    §82b spreading is noted per row, not applied), grouped per property with
    subtotals and a grand total."""
    from pdfgen import generate_expense_inventory
    rows = fetch("""
        SELECT p.name, a.name, e.expense_date, e.amount, e.category,
               e.vendor, e.note, e.distribute_years, e.source_file, e.property_id
        FROM expenses e
        JOIN properties p ON p.id = e.property_id
        LEFT JOIN apartments a ON a.id = e.apartment_id
        WHERE substr(e.expense_date,1,4) = ? AND e.owner_id = ?
        ORDER BY p.name, e.expense_date
    """, (str(year), owner))
    groups: dict[int, dict] = {}
    grand_total = 0.0
    for pname, aname, edate, amount, cat, vendor, note, dyears, src, pid in rows:
        if property_id is not None and pid != property_id:
            continue
        amount = float(amount)
        dyears = int(dyears or 1)
        # Group by property id, not name: two distinct properties (e.g. two WEs
        # at the same address) may share a display name but must never merge.
        g = groups.setdefault(pid, {"property_name": pname, "rows": [], "subtotal": 0.0})
        g["rows"].append({
            "expense_date": edate, "amount": amount, "category": cat,
            "vendor": _clean(vendor), "apartment_name": _clean(aname),
            "source_file": _clean(src), "distribute_years": dyears,
            "share_this_year": round(amount / dyears, 2),
        })
        g["subtotal"] = round(g["subtotal"] + amount, 2)
        grand_total = round(grand_total + amount, 2)
    if not groups:
        scope = f"property {property_id} in {year}" if property_id is not None else str(year)
        raise HTTPException(status_code=404, detail=f"No expenses recorded for {scope}")
    pdf_bytes = generate_expense_inventory(year, list(groups.values()), grand_total)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="Belegliste_{year}.pdf"',
    })


# ── Kaltmiete / NK split per contract ────────────────────────────────────────

@router.get("/nk-splits")
def list_nk_splits(owner: int = Depends(require_auth)):
    """Contracts with their monthly NK-Vorauszahlung portion, for the
    Kaltmiete/Umlagen income split. Ended contracts still matter for past
    tax years, so all contracts are returned."""
    rows = fetch("""
        SELECT c.id, t.name, a.name, a.property_id, p.name, c.rent,
               c.nebenkosten_vorauszahlung, c.start_date, c.end_date, c.nk_mode
        FROM contracts c
        JOIN tenants t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE c.owner_id = ?
        ORDER BY p.name, t.name
    """, (owner,))
    return [{
        "contract_id": r[0], "tenant_name": r[1], "apartment_name": r[2],
        "property_id": r[3], "property_name": r[4],
        "rent": float(r[5] or 0),
        "nebenkosten_vorauszahlung": float(r[6]) if r[6] is not None else None,
        "kaltmiete": round(float(r[5] or 0) - float(r[6]), 2) if r[6] is not None else None,
        "start_date": r[7], "end_date": _clean(r[8]),
        "nk_mode": r[9] or "prepayment",
    } for r in rows]


@router.put("/nk-splits/{contract_id}")
def set_nk_split(contract_id: int, body: NkSplitIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner)):
        raise HTTPException(status_code=404, detail="Contract not found")
    execute("UPDATE contracts SET nebenkosten_vorauszahlung=?, "
            "nk_mode=COALESCE(?, nk_mode) WHERE id=? AND owner_id=?",
            (body.nebenkosten_vorauszahlung, body.nk_mode, contract_id, owner))
    return {"contract_id": contract_id,
            "nebenkosten_vorauszahlung": body.nebenkosten_vorauszahlung,
            "nk_mode": body.nk_mode}


# ── Overrides ────────────────────────────────────────────────────────────────

@router.put("/overrides/{property_id}/{tax_year}")
def set_override(property_id: int, tax_year: int, body: OverrideIn,
                 owner: int = Depends(require_auth)):
    if body.field not in OVERRIDE_FIELDS:
        raise HTTPException(status_code=422,
                            detail=f"Unknown override field; allowed: {sorted(OVERRIDE_FIELDS)}")
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    execute("DELETE FROM tax_year_overrides WHERE property_id=? AND tax_year=? AND field=? AND owner_id=?",
            (property_id, tax_year, body.field, owner))
    if body.value is not None:
        insert("tax_year_overrides", (property_id, tax_year, body.field, body.value, body.note))
    return {"property_id": property_id, "tax_year": tax_year,
            "field": body.field, "value": body.value}


# ── The report ───────────────────────────────────────────────────────────────

def _afa_items(afa: dict, ov) -> list[dict]:
    """Transparent AfA line items [{label, amount}] — e.g. Gebäude + Einbauküche.
    An override's note may carry a JSON list; otherwise a single line is returned."""
    if ov is not None:
        note = ov[1]
        if note:
            try:
                parsed = json.loads(note)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                out = []
                for it in parsed:
                    try:
                        out.append({"label": str(it.get("label", "AfA")),
                                    "amount": round(float(it["amount"]), 2)})
                    except Exception:
                        continue
                if out:
                    return out
        return [{"label": "AfA (manuell)", "amount": afa["afa"]}]
    if afa.get("source") == "computed":
        return [{"label": "Gebäude-AfA", "amount": afa["afa"]}]
    return []


def build_report(year: int, owner: int) -> tuple[list[dict], list[str]]:
    """Returns (per-property blocks for tax-relevant properties,
    names of excluded properties) for the given owner."""
    # Seven independent loads, one round trip. Each selects a single
    # json_build_array so the rows stay positional (see db.fetch_bundle).
    loaded = fetch_bundle([
        ("props", "SELECT json_build_array(id, name, COALESCE(tax_relevant,1)) "
                  "FROM properties WHERE owner_id=? ORDER BY name", (owner,)),
        ("profiles", "SELECT json_build_array(property_id, purchase_date, purchase_price,"
                     " building_share_pct, afa_rate_pct) "
                     "FROM property_tax_profiles WHERE owner_id=?", (owner,)),
        ("mortgages", f"SELECT json_build_array({_MORTGAGE_COLS}) FROM mortgages "
                      "WHERE owner_id=? ORDER BY id", (owner,)),
        ("money", """
            SELECT json_build_array(property_id, kind, total, cnt) FROM (
                SELECT a.property_id, pm.kind AS kind, COALESCE(SUM(pm.amount),0) AS total,
                       COUNT(pm.id) AS cnt
                FROM payments pm
                JOIN contracts c ON c.id = pm.contract_id
                JOIN apartments a ON a.id = c.apartment_id
                WHERE substr(pm.payment_date,1,4) = ? AND pm.owner_id = ?
                GROUP BY a.property_id, pm.kind
                UNION ALL
                SELECT a.property_id, 'nk_settlement', COALESCE(SUM(d.amount),0), COUNT(d.id)
                FROM kaution_deductions d
                JOIN contracts c ON c.id = d.contract_id
                JOIN apartments a ON a.id = c.apartment_id
                WHERE substr(d.date,1,4) = ? AND d.owner_id = ?
                  AND (d.category = ? OR d.reference_type = ?)
                GROUP BY a.property_id
                UNION ALL
                SELECT a.property_id, 'deposit_rent', COALESCE(SUM(d.amount),0), COUNT(d.id)
                FROM kaution_deductions d
                JOIN contracts c ON c.id = d.contract_id
                JOIN apartments a ON a.id = c.apartment_id
                WHERE substr(d.date,1,4) = ? AND d.owner_id = ?
                  AND d.category IN (?, ?)
                  AND COALESCE(d.reference_type, '') <> ?
                GROUP BY a.property_id
            ) m""", (str(year), owner, str(year), owner, NK_CATEGORY, NK_REF_TYPE,
                     str(year), owner, *RENT_CATEGORIES, NK_REF_TYPE)),
        ("contracts", """
            SELECT json_build_array(a.property_id, t.name, c.rent, c.start_date, c.end_date,
                                    c.nebenkosten_vorauszahlung)
            FROM contracts c
            JOIN apartments a ON a.id = c.apartment_id
            JOIN tenants t ON t.id = c.tenant_id
            WHERE c.owner_id = ?""", (owner,)),
        ("flat", """
            SELECT json_build_array(a.property_id, fc.cost_type, fc.amount, fc.valid_from,
                                    fc.valid_to, COALESCE(fc.frequency, 'monthly'))
            FROM flat_costs fc JOIN apartments a ON a.id = fc.apartment_id
            WHERE fc.owner_id = ?""", (owner,)),
        ("overrides", "SELECT json_build_array(property_id, field, value, note) "
                      "FROM tax_year_overrides WHERE tax_year=? AND owner_id=?", (year, owner)),
    ])

    all_props = loaded["props"]
    props = [(pid, name) for pid, name, rel in all_props if rel]
    excluded = [name for _, name, rel in all_props if not rel]
    profiles = {r[0]: r for r in loaded["profiles"]}
    mortgages: dict[int, list] = {}
    for r in loaded["mortgages"]:
        mortgages.setdefault(r[1], []).append(_mortgage_row(r))

    # Rent and NK settlements apart. Whether income comes from payments or
    # from the contract estimate is decided by the rent alone — a lone
    # Nachzahlung must not switch a property with no rent recorded over to
    # "payments" and report the Nachzahlung as the year's whole income.
    # Settlements are cash in the year they move (§11 EStG) and are Umlagen.
    # That includes a Nachzahlung kept back from the deposit: the offset is
    # when it is received, so those Kaution deductions count here too.
    #
    # Rent kept from the deposit (a Mietrückstand, or an agreed Abwohnen) is
    # rent received on the deduction date. It comes back as kind 'deposit_rent'
    # and is added only when income comes from payments: the contract
    # estimate already assumes every month's rent arrived.
    pay: dict[int, tuple] = {}
    settle: dict[int, float] = {}
    rent_deposit: dict[int, float] = {}
    for pid_, kind, total, cnt in loaded["money"]:
        if kind == "nk_settlement":
            settle[pid_] = settle.get(pid_, 0.0) + float(total)
        elif kind == "deposit_rent":
            rent_deposit[pid_] = float(total)
        else:
            pay[pid_] = (float(total), int(cnt))

    contracts: dict[int, list] = {}
    for r in loaded["contracts"]:
        contracts.setdefault(r[0], []).append(r)

    flat: dict[int, list] = {}
    for r in loaded["flat"]:
        flat.setdefault(r[0], []).append(r)

    expenses: dict[int, list] = {}
    for e in list_expenses(year=year, owner=owner):
        if e["deductible"]:
            expenses.setdefault(e["property_id"], []).append(e)

    overrides: dict[tuple, tuple] = {}
    for r in loaded["overrides"]:
        overrides[(r[0], r[1])] = (float(r[2]), _clean(r[3]))

    report = []
    for pid, name in props:
        # Income — payments if any exist for this property+year, else estimate.
        auto_total, pay_count = pay.get(pid, (0.0, 0))
        est_rows = []
        umlagen_total = 0.0
        # Trust the Kaltmiete/Umlagen derivation only when at least one
        # contract was active in the year AND every active one has its NK
        # portion set — otherwise a data gap would masquerade as "Umlagen 0".
        active_contracts = 0
        nk_missing = 0
        for _, tenant, rent, cs, ce, nk in contracts.get(pid, []):
            months = tax_logic.contract_months_in_year(cs, _clean(ce), year)
            if months > 0 and rent:
                active_contracts += 1
                est_rows.append({"tenant": tenant, "months": months,
                                 "rent": float(rent), "total": round(float(rent) * months, 2)})
                if nk is None:
                    nk_missing += 1
                else:
                    umlagen_total += float(nk) * months
        nk_known = active_contracts > 0 and nk_missing == 0
        umlagen_total = round(umlagen_total, 2)
        estimate_total = round(sum(r["total"] for r in est_rows), 2)
        settlements = round(settle.get(pid, 0.0), 2)
        from_deposit = round(rent_deposit.get(pid, 0.0), 2) if pay_count > 0 else 0.0
        ov = overrides.get((pid, "income_total"))
        if ov is not None:
            income_final, income_source = ov[0], "override"
        elif pay_count > 0:
            income_final, income_source = (round(auto_total + from_deposit + settlements, 2),
                                           "payments")
        else:
            income_final, income_source = round(estimate_total + settlements, 2), "estimate"
        # Both a Nachzahlung and a refund belong on the Umlagen line; the
        # contractual prepayments alone would push them into the Kaltmiete.
        umlagen_total = round(umlagen_total + settlements, 2)
        # Kaltmiete/Umlagen split (separate Anlage V lines; the sum is
        # unchanged). Umlagen come from the contractual monthly NK
        # prepayments; only trustworthy when every active contract has one.
        # A manual income_kaltmiete override wins over the derivation.
        ov_kalt = overrides.get((pid, "income_kaltmiete"))
        if ov_kalt is not None:
            kaltmiete = ov_kalt[0]
            umlagen_total = round(income_final - kaltmiete, 2)
            nk_known, split_source = True, "override"
        elif nk_known:
            kaltmiete = round(income_final - umlagen_total, 2)
            split_source = "contracts"
        else:
            kaltmiete, split_source = None, None

        # AfA — manual override wins over the profile computation.
        p = profiles.get(pid)
        afa = {"afa": 0.0, "complete": False, "source": "incomplete"}
        if p and all(v is not None for v in (p[1], p[2], p[3], p[4])) and _clean(p[1]):
            afa = {**tax_logic.afa_for_year(float(p[2]), float(p[3]), float(p[4]), p[1], year),
                   "complete": True, "source": "computed"}
        ov_afa = overrides.get((pid, "afa"))
        if ov_afa is not None:
            afa = {**afa, "computed_afa": afa["afa"], "afa": ov_afa[0], "source": "override"}
        afa["items"] = _afa_items(afa, ov_afa)

        # Schuldzinsen — manual expense rows win over the annuity computation.
        zins_rows = [e for e in expenses.get(pid, []) if e["category"] == "Schuldzinsen"]
        computed_rows = []
        for m in mortgages.get(pid, []):
            b = tax_logic.year_breakdown_for(m, year)
            computed_rows.append({"label": m["label"] or f"Loan #{m['id']}", **b})
        ov_zins = overrides.get((pid, "schuldzinsen"))
        if ov_zins is not None:
            zins_final, zins_source = ov_zins[0], "override"
        elif zins_rows:
            zins_final = round(sum(tax_logic.expense_share_for_year(
                e["expense_date"], e["amount"], e["distribute_years"], year)
                for e in zins_rows), 2)
            zins_source = "manual"
        else:
            zins_final = round(sum(c["interest"] for c in computed_rows), 2)
            zins_source = "computed" if computed_rows else "none"

        # Recurring flat costs
        recurring, recurring_total = [], 0.0
        for _, cost_type, amount, vf, vt, freq in flat.get(pid, []):
            months = tax_logic.months_active_in_year(_clean(vf), _clean(vt), year)
            if months == 0:
                continue
            deductible = cost_type not in NON_DEDUCTIBLE_COST_TYPES
            if freq == "one-time":
                # Paid once, in the year it is dated. Undated: cannot be
                # attributed to any year, so it is left out rather than
                # guessed into every year.
                paid_on = tax_logic._parse(_clean(vf))
                if paid_on is None or paid_on.year != year:
                    continue
                monthly, months = float(amount), 1
            else:
                # A quarterly or annual bill is spread over its months; before
                # this the amount was multiplied by 12 whatever the frequency,
                # overstating an annual Grundsteuer twelvefold.
                monthly = tax_logic.monthly_equivalent(float(amount), freq)
            total = round(monthly * months, 2)
            recurring.append({"cost_type": cost_type, "monthly": round(monthly, 2),
                              "frequency": freq, "months": months, "total": total,
                              "deductible": deductible})
            if deductible:
                recurring_total += total
        recurring_total = round(recurring_total, 2)
        ov_rec = overrides.get((pid, "recurring_total"))
        recurring_computed = recurring_total
        if ov_rec is not None:
            recurring_total, recurring_source = ov_rec[0], "override"
        else:
            recurring_source = "computed"

        # One-off expenses (Schuldzinsen rows live in the Schuldzinsen block)
        one_off, one_off_total = [], 0.0
        for e in expenses.get(pid, []):
            if e["category"] == "Schuldzinsen":
                continue
            share = tax_logic.expense_share_for_year(
                e["expense_date"], e["amount"], e["distribute_years"], year)
            one_off.append({**e, "share_this_year": share})
            one_off_total += share
        one_off_total = round(one_off_total, 2)

        wk_total = round(afa["afa"] + zins_final + recurring_total + one_off_total, 2)
        report.append({
            "property_id": pid, "property_name": name,
            "income": {
                "final": income_final, "source": income_source,
                "payments_total": round(auto_total, 2), "payments_count": pay_count,
                "estimate_total": estimate_total, "estimate_rows": est_rows,
                "override_note": ov[1] if ov else None,
                "nk_known": nk_known,
                "umlagen": umlagen_total if nk_known else None,
                "nk_settlements": settlements,
                # Rent kept from the deposit, already inside `final` (and the Kaltmiete).
                "rent_from_deposit": from_deposit,
                "kaltmiete": kaltmiete,
                "split_source": split_source,
            },
            "werbungskosten": {
                "afa": afa,
                "schuldzinsen": {"final": zins_final, "source": zins_source,
                                 "computed": computed_rows},
                "recurring": recurring, "recurring_total": recurring_total,
                "recurring_computed": recurring_computed,
                "recurring_source": recurring_source,
                "one_off": one_off, "one_off_total": one_off_total,
                "total": wk_total,
            },
            "result": round(income_final - wk_total, 2),
        })
    return report, excluded


@router.get("/report")
def tax_report(year: int = _Year, owner: int = Depends(require_auth)):
    blocks, excluded = build_report(year, owner)
    return {
        "year": year,
        "properties": blocks,
        "excluded_properties": excluded,
        "totals": {
            "income": round(sum(b["income"]["final"] for b in blocks), 2),
            "werbungskosten": round(sum(b["werbungskosten"]["total"] for b in blocks), 2),
            "result": round(sum(b["result"] for b in blocks), 2),
        },
    }


@router.get("/report/pdf")
def tax_report_pdf(year: int = _Year, property_id: int | None = None,
                   owner: int = Depends(require_auth)):
    from pdfgen import generate_tax_report
    blocks, _ = build_report(year, owner)
    if property_id is not None:
        blocks = [b for b in blocks if b["property_id"] == property_id]
        if not blocks:
            raise HTTPException(status_code=404, detail="Property not found")
    pdf_bytes = generate_tax_report(year, blocks)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="Anlage_V_Ausfuellhilfe_{year}.pdf"',
    })
