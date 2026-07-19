"""Anlage-V helper endpoints (docs/PRD-tax-module.md).

Report philosophy: every euro in the output is traceable — each block carries
its source rows ("derivation"), and figures the DB can't know (gap-year income,
Sondertilgung-affected interest) are overridable per (property, year, field)
via tax_year_overrides. Manual always wins over computed.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from db import fetch, execute, insert
import tax_logic

router = APIRouter(prefix="/tax", tags=["Tax"])

# Which recurring flat_costs count as Werbungskosten by default.
# "Miete" is the landlord's own rent cost type (not a letting expense);
# "Mortgage" mixes Tilgung into the amount — interest is handled via the
# mortgages table / Schuldzinsen instead, so it must not be summed here.
NON_DEDUCTIBLE_COST_TYPES = {"Miete", "Mortgage"}

EXPENSE_CATEGORIES = [
    "Erhaltungsaufwand", "Renovierung", "Instandhaltung",
    "Schuldzinsen", "Geldbeschaffungskosten",
    "Grundsteuer", "Versicherung", "Verwaltung", "Hausgeld",
    "Fahrtkosten", "Sonstige",
]


# ── Schemas ──────────────────────────────────────────────────────────────────

class TaxProfileIn(BaseModel):
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    building_share_pct: Optional[float] = None
    afa_rate_pct: Optional[float] = None
    notes: Optional[str] = None


class MortgageIn(BaseModel):
    property_id: int
    label: Optional[str] = None
    principal: float
    interest_rate_pct: float
    tilgung_rate_pct: float
    start_date: str
    note: Optional[str] = None


class ExpenseIn(BaseModel):
    property_id: int
    apartment_id: Optional[int] = None
    expense_date: str
    amount: float
    category: str
    vendor: Optional[str] = None
    note: Optional[str] = None
    deductible: int = 1
    distribute_years: int = 1
    source_file: Optional[str] = None  # scanned receipt this row came from


class NkSplitIn(BaseModel):
    nebenkosten_vorauszahlung: Optional[float] = None  # None clears


class OverrideIn(BaseModel):
    field: str
    value: Optional[float] = None  # None deletes the override
    note: Optional[str] = None


class RelevanceIn(BaseModel):
    tax_relevant: bool


def _clean(v):
    return None if v is None or v == "None" else v


# ── Profiles + mortgages ─────────────────────────────────────────────────────

def _mortgage_row(r) -> dict:
    return {
        "id": r[0], "property_id": r[1], "label": _clean(r[2]),
        "principal": float(r[3]), "interest_rate_pct": float(r[4]),
        "tilgung_rate_pct": float(r[5]), "start_date": r[6], "note": _clean(r[7]),
    }


@router.get("/profiles")
def list_profiles():
    props = fetch("SELECT id, name, COALESCE(tax_relevant,1) FROM properties ORDER BY name")
    profiles = {r[0]: r for r in fetch(
        "SELECT property_id, purchase_date, purchase_price, building_share_pct,"
        "       afa_rate_pct, notes FROM property_tax_profiles")}
    mortgages: dict[int, list] = {}
    for r in fetch("SELECT id, property_id, label, principal, interest_rate_pct,"
                   "       tilgung_rate_pct, start_date, note FROM mortgages ORDER BY id"):
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
def upsert_profile(property_id: int, body: TaxProfileIn):
    if not fetch("SELECT id FROM properties WHERE id=?", (property_id,)):
        raise HTTPException(status_code=404, detail="Property not found")
    vals = (body.purchase_date, body.purchase_price, body.building_share_pct,
            body.afa_rate_pct, body.notes)
    if fetch("SELECT id FROM property_tax_profiles WHERE property_id=?", (property_id,)):
        execute("""UPDATE property_tax_profiles SET purchase_date=?, purchase_price=?,
                   building_share_pct=?, afa_rate_pct=?, notes=? WHERE property_id=?""",
                (*vals, property_id))
    else:
        insert("property_tax_profiles", (property_id, *vals))
    return {"property_id": property_id, **body.model_dump()}


@router.put("/properties/{property_id}/relevance")
def set_tax_relevance(property_id: int, body: RelevanceIn):
    """Include/exclude a property from the tax report (e.g. managed for
    someone else). Separate from the profile upsert so a toggle can never
    clobber purchase data."""
    if not fetch("SELECT id FROM properties WHERE id=?", (property_id,)):
        raise HTTPException(status_code=404, detail="Property not found")
    execute("UPDATE properties SET tax_relevant=? WHERE id=?",
            (1 if body.tax_relevant else 0, property_id))
    return {"property_id": property_id, "tax_relevant": body.tax_relevant}


@router.post("/mortgages", status_code=201)
def create_mortgage(body: MortgageIn):
    if not fetch("SELECT id FROM properties WHERE id=?", (body.property_id,)):
        raise HTTPException(status_code=404, detail="Property not found")
    insert("mortgages", (body.property_id, body.label, body.principal,
                         body.interest_rate_pct, body.tilgung_rate_pct,
                         body.start_date, body.note))
    r = fetch("SELECT id, property_id, label, principal, interest_rate_pct, tilgung_rate_pct,"
              "       start_date, note FROM mortgages ORDER BY id DESC LIMIT 1")[0]
    return _mortgage_row(r)


@router.put("/mortgages/{mortgage_id}")
def update_mortgage(mortgage_id: int, body: MortgageIn):
    if not fetch("SELECT id FROM mortgages WHERE id=?", (mortgage_id,)):
        raise HTTPException(status_code=404, detail="Mortgage not found")
    execute("""UPDATE mortgages SET property_id=?, label=?, principal=?, interest_rate_pct=?,
               tilgung_rate_pct=?, start_date=?, note=? WHERE id=?""",
            (body.property_id, body.label, body.principal, body.interest_rate_pct,
             body.tilgung_rate_pct, body.start_date, body.note, mortgage_id))
    r = fetch("SELECT id, property_id, label, principal, interest_rate_pct, tilgung_rate_pct,"
              "       start_date, note FROM mortgages WHERE id=?", (mortgage_id,))[0]
    return _mortgage_row(r)


@router.delete("/mortgages/{mortgage_id}", status_code=204)
def delete_mortgage(mortgage_id: int):
    if not fetch("SELECT id FROM mortgages WHERE id=?", (mortgage_id,)):
        raise HTTPException(status_code=404, detail="Mortgage not found")
    execute("DELETE FROM mortgages WHERE id=?", (mortgage_id,))


# ── Expenses ─────────────────────────────────────────────────────────────────

_EXPENSE_SELECT = """
    SELECT e.id, e.property_id, p.name, e.apartment_id, e.expense_date, e.amount,
           e.category, e.vendor, e.note, e.deductible, e.distribute_years, e.source_file
    FROM expenses e JOIN properties p ON p.id = e.property_id
"""


def _expense_row(r) -> dict:
    return {
        "id": r[0], "property_id": r[1], "property_name": r[2],
        "apartment_id": r[3], "expense_date": r[4], "amount": float(r[5]),
        "category": r[6], "vendor": _clean(r[7]), "note": _clean(r[8]),
        "deductible": int(r[9] or 0), "distribute_years": int(r[10] or 1),
        "source_file": _clean(r[11]),
    }


@router.get("/expenses")
def list_expenses(year: int | None = None, property_id: int | None = None):
    rows = [_expense_row(r) for r in fetch(f"{_EXPENSE_SELECT} ORDER BY e.expense_date DESC")]
    if property_id:
        rows = [r for r in rows if r["property_id"] == property_id]
    if year:
        # Include rows whose §82b spreading window touches the year.
        rows = [r for r in rows if tax_logic.expense_share_for_year(
            r["expense_date"], r["amount"], r["distribute_years"], year) > 0]
    return rows


@router.post("/expenses", status_code=201)
def create_expense(body: ExpenseIn):
    if not fetch("SELECT id FROM properties WHERE id=?", (body.property_id,)):
        raise HTTPException(status_code=404, detail="Property not found")
    insert("expenses", (body.property_id, body.apartment_id, body.expense_date,
                        body.amount, body.category, body.vendor, body.note,
                        body.deductible, body.distribute_years, body.source_file))
    r = fetch(f"{_EXPENSE_SELECT} ORDER BY e.id DESC LIMIT 1")[0]
    return _expense_row(r)


@router.put("/expenses/{expense_id}")
def update_expense(expense_id: int, body: ExpenseIn):
    if not fetch("SELECT id FROM expenses WHERE id=?", (expense_id,)):
        raise HTTPException(status_code=404, detail="Expense not found")
    execute("""UPDATE expenses SET property_id=?, apartment_id=?, expense_date=?, amount=?,
               category=?, vendor=?, note=?, deductible=?, distribute_years=?, source_file=?
               WHERE id=?""",
            (body.property_id, body.apartment_id, body.expense_date, body.amount,
             body.category, body.vendor, body.note, body.deductible,
             body.distribute_years, body.source_file, expense_id))
    r = fetch(f"{_EXPENSE_SELECT} WHERE e.id=?", (expense_id,))[0]
    return _expense_row(r)


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int):
    if not fetch("SELECT id FROM expenses WHERE id=?", (expense_id,)):
        raise HTTPException(status_code=404, detail="Expense not found")
    execute("DELETE FROM expenses WHERE id=?", (expense_id,))


@router.get("/expense-categories")
def expense_categories():
    return EXPENSE_CATEGORIES


# ── Kaltmiete / NK split per contract ────────────────────────────────────────

@router.get("/nk-splits")
def list_nk_splits():
    """Contracts with their monthly NK-Vorauszahlung portion, for the
    Kaltmiete/Umlagen income split. Ended contracts still matter for past
    tax years, so all contracts are returned."""
    rows = fetch("""
        SELECT c.id, t.name, a.name, a.property_id, p.name, c.rent,
               c.nebenkosten_vorauszahlung, c.start_date, c.end_date
        FROM contracts c
        JOIN tenants t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        ORDER BY p.name, t.name
    """)
    return [{
        "contract_id": r[0], "tenant_name": r[1], "apartment_name": r[2],
        "property_id": r[3], "property_name": r[4],
        "rent": float(r[5] or 0),
        "nebenkosten_vorauszahlung": float(r[6]) if r[6] is not None else None,
        "kaltmiete": round(float(r[5] or 0) - float(r[6]), 2) if r[6] is not None else None,
        "start_date": r[7], "end_date": _clean(r[8]),
    } for r in rows]


@router.put("/nk-splits/{contract_id}")
def set_nk_split(contract_id: int, body: NkSplitIn):
    if not fetch("SELECT id FROM contracts WHERE id=?", (contract_id,)):
        raise HTTPException(status_code=404, detail="Contract not found")
    execute("UPDATE contracts SET nebenkosten_vorauszahlung=? WHERE id=?",
            (body.nebenkosten_vorauszahlung, contract_id))
    return {"contract_id": contract_id,
            "nebenkosten_vorauszahlung": body.nebenkosten_vorauszahlung}


# ── Overrides ────────────────────────────────────────────────────────────────

@router.put("/overrides/{property_id}/{tax_year}")
def set_override(property_id: int, tax_year: int, body: OverrideIn):
    if not fetch("SELECT id FROM properties WHERE id=?", (property_id,)):
        raise HTTPException(status_code=404, detail="Property not found")
    execute("DELETE FROM tax_year_overrides WHERE property_id=? AND tax_year=? AND field=?",
            (property_id, tax_year, body.field))
    if body.value is not None:
        insert("tax_year_overrides", (property_id, tax_year, body.field, body.value, body.note))
    return {"property_id": property_id, "tax_year": tax_year,
            "field": body.field, "value": body.value}


# ── The report ───────────────────────────────────────────────────────────────

def build_report(year: int) -> tuple[list[dict], list[str]]:
    """Returns (per-property blocks for tax-relevant properties,
    names of excluded properties)."""
    all_props = fetch("SELECT id, name, COALESCE(tax_relevant,1) FROM properties ORDER BY name")
    props = [(pid, name) for pid, name, rel in all_props if rel]
    excluded = [name for _, name, rel in all_props if not rel]
    profiles = {r[0]: r for r in fetch(
        "SELECT property_id, purchase_date, purchase_price, building_share_pct,"
        "       afa_rate_pct FROM property_tax_profiles")}
    mortgages: dict[int, list] = {}
    for r in fetch("SELECT id, property_id, label, principal, interest_rate_pct,"
                   "       tilgung_rate_pct, start_date, note FROM mortgages ORDER BY id"):
        mortgages.setdefault(r[1], []).append(_mortgage_row(r))

    pay = {r[0]: (float(r[1]), int(r[2])) for r in fetch("""
        SELECT a.property_id, COALESCE(SUM(pm.amount),0), COUNT(pm.id)
        FROM payments pm
        JOIN contracts c ON c.id = pm.contract_id
        JOIN apartments a ON a.id = c.apartment_id
        WHERE substr(pm.payment_date,1,4) = ?
        GROUP BY a.property_id
    """, (str(year),))}

    contracts: dict[int, list] = {}
    for r in fetch("""
        SELECT a.property_id, t.name, c.rent, c.start_date, c.end_date,
               c.nebenkosten_vorauszahlung
        FROM contracts c
        JOIN apartments a ON a.id = c.apartment_id
        JOIN tenants t ON t.id = c.tenant_id
    """):
        contracts.setdefault(r[0], []).append(r)

    flat: dict[int, list] = {}
    for r in fetch("""
        SELECT a.property_id, fc.cost_type, fc.amount, fc.valid_from, fc.valid_to
        FROM flat_costs fc JOIN apartments a ON a.id = fc.apartment_id
    """):
        flat.setdefault(r[0], []).append(r)

    expenses: dict[int, list] = {}
    for e in list_expenses(year=year):
        if e["deductible"]:
            expenses.setdefault(e["property_id"], []).append(e)

    overrides: dict[tuple, tuple] = {}
    for r in fetch("SELECT property_id, field, value, note FROM tax_year_overrides"
                   " WHERE tax_year=?", (year,)):
        overrides[(r[0], r[1])] = (float(r[2]), _clean(r[3]))

    report = []
    for pid, name in props:
        # Income — payments if any exist for this property+year, else estimate.
        auto_total, pay_count = pay.get(pid, (0.0, 0))
        est_rows = []
        umlagen_total = 0.0
        nk_known = bool(contracts.get(pid))
        for _, tenant, rent, cs, ce, nk in contracts.get(pid, []):
            months = tax_logic.contract_months_in_year(cs, _clean(ce), year)
            if months > 0 and rent:
                est_rows.append({"tenant": tenant, "months": months,
                                 "rent": float(rent), "total": round(float(rent) * months, 2)})
                if nk is None:
                    nk_known = False
                else:
                    umlagen_total += float(nk) * months
        umlagen_total = round(umlagen_total, 2)
        estimate_total = round(sum(r["total"] for r in est_rows), 2)
        ov = overrides.get((pid, "income_total"))
        if ov is not None:
            income_final, income_source = ov[0], "override"
        elif pay_count > 0:
            income_final, income_source = round(auto_total, 2), "payments"
        else:
            income_final, income_source = estimate_total, "estimate"
        # Kaltmiete/Umlagen split (separate Anlage V lines; the sum is
        # unchanged). Umlagen come from the contractual monthly NK
        # prepayments; only trustworthy when every active contract has one.
        kaltmiete = round(income_final - umlagen_total, 2) if nk_known else None

        # AfA
        p = profiles.get(pid)
        afa = {"afa": 0.0, "complete": False}
        if p and all(v is not None for v in (p[1], p[2], p[3], p[4])) and _clean(p[1]):
            afa = {**tax_logic.afa_for_year(float(p[2]), float(p[3]), float(p[4]), p[1], year),
                   "complete": True}

        # Schuldzinsen — manual expense rows win over the annuity computation.
        zins_rows = [e for e in expenses.get(pid, []) if e["category"] == "Schuldzinsen"]
        computed_rows = []
        for m in mortgages.get(pid, []):
            b = tax_logic.annuity_year_breakdown(
                m["principal"], m["interest_rate_pct"], m["tilgung_rate_pct"],
                m["start_date"], year)
            computed_rows.append({"label": m["label"] or f"Loan #{m['id']}", **b})
        if zins_rows:
            zins_final = round(sum(tax_logic.expense_share_for_year(
                e["expense_date"], e["amount"], e["distribute_years"], year)
                for e in zins_rows), 2)
            zins_source = "manual"
        else:
            zins_final = round(sum(c["interest"] for c in computed_rows), 2)
            zins_source = "computed" if computed_rows else "none"

        # Recurring flat costs
        recurring, recurring_total = [], 0.0
        for _, cost_type, amount, vf, vt in flat.get(pid, []):
            months = tax_logic.months_active_in_year(_clean(vf), _clean(vt), year)
            if months == 0:
                continue
            deductible = cost_type not in NON_DEDUCTIBLE_COST_TYPES
            total = round(float(amount) * months, 2)
            recurring.append({"cost_type": cost_type, "monthly": float(amount),
                              "months": months, "total": total, "deductible": deductible})
            if deductible:
                recurring_total += total
        recurring_total = round(recurring_total, 2)

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
                "kaltmiete": kaltmiete,
            },
            "werbungskosten": {
                "afa": afa,
                "schuldzinsen": {"final": zins_final, "source": zins_source,
                                 "computed": computed_rows},
                "recurring": recurring, "recurring_total": recurring_total,
                "one_off": one_off, "one_off_total": one_off_total,
                "total": wk_total,
            },
            "result": round(income_final - wk_total, 2),
        })
    return report, excluded


@router.get("/report")
def tax_report(year: int):
    blocks, excluded = build_report(year)
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
def tax_report_pdf(year: int, property_id: int | None = None):
    from pdfgen import generate_tax_report
    blocks, _ = build_report(year)
    if property_id is not None:
        blocks = [b for b in blocks if b["property_id"] == property_id]
        if not blocks:
            raise HTTPException(status_code=404, detail="Property not found")
    pdf_bytes = generate_tax_report(year, blocks)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="Anlage_V_Ausfuellhilfe_{year}.pdf"',
    })
