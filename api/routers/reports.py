"""PDF generation, calculation, and report endpoints."""
from datetime import date
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, Any
from db import get_config, fetch, execute, get_conn, put_conn

router = APIRouter(prefix="/reports", tags=["Reports"])

_SIG_PATH = "pdf/signature.png"


def _sig() -> str | None:
    return _SIG_PATH if Path(_SIG_PATH).exists() else None


def _landlord_name() -> str:
    return get_config("landlord_name", "Hausverwaltung")


# ── Balance Sheet ─────────────────────────────────────────────────────────────

@router.get("/balance-sheet/{year}")
def balance_sheet_data(year: int):
    from page_modules.balance_sheet import _compute_snapshot
    snapshot, props = _compute_snapshot(year)
    # serialise Decimal values for JSON
    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return v
    props_clean = []
    for p in props:
        rows_clean = [{k: _f(vv) for k, vv in row.items()} for row in p["monthly_rows"]]
        props_clean.append({**p, "monthly_rows": rows_clean,
                             "tot_expected": _f(p["tot_expected"]),
                             "tot_actual": _f(p["tot_actual"]),
                             "tot_costs": _f(p["tot_costs"])})
    snap_clean = [{k: _f(v) for k, v in s.items()} for s in snapshot]
    return {"year": year, "snapshot": snap_clean, "properties": props_clean}


@router.get("/balance-sheet/{year}/pdf")
def balance_sheet_pdf(year: int):
    from page_modules.balance_sheet import _compute_snapshot
    from pdfgen import balance_sheet_pdf as gen_pdf
    snapshot, props = _compute_snapshot(year)
    pdf_bytes = gen_pdf(year, snapshot, props, landlord_name=_landlord_name(), signature_path=_sig())
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Bilanz_{year}.pdf"'})


# ── Nebenkostenabrechnung calculation ─────────────────────────────────────────

class NKCalcRequest(BaseModel):
    strom: Optional[Any] = None
    gas: Optional[Any] = None
    water: Optional[Any] = None
    warmwater: Optional[Any] = None
    heizung: Optional[Any] = None
    bk: Optional[Any] = None


@router.post("/nebenkostenabrechnung/calculate")
def nk_calculate(body: NKCalcRequest):
    from logic import (strom_calc_detail, gas_calc_detail, water_calc_detail,
                       warmwasser_calc_detail, heizung_calc_detail, betriebskosten_calc)
    result = {}
    if body.strom:
        s = body.strom
        result["strom"] = strom_calc_detail(
            s["start_kwh"], s["end_kwh"], s["arbeitspreis"], s["grundpreis_monthly"],
            s["num_tenants"], s["bill_days"], s["eff_days"], s["prepay_monthly"],
            s.get("is_pauschale", False))
    if body.gas:
        g = body.gas
        result["gas"] = gas_calc_detail(
            g["start_m3"], g["end_m3"], g["umrechnungsfaktor"], g["arbeitspreis"],
            g["grundpreis_monthly"], g["num_tenants"], g["bill_days"],
            g["eff_days"], g["prepay_monthly"], g.get("is_pauschale", False))
    if body.water:
        w = body.water
        result["water"] = water_calc_detail(
            w["start_m3"], w["end_m3"], w["frischwasser_per_m3"], w["abwasser_per_m3"],
            w["num_tenants"], w["bill_days"], w["eff_days"],
            w["prepay_monthly"], w.get("is_pauschale", False))
    if body.warmwater:
        ww = body.warmwater
        result["warmwater"] = warmwasser_calc_detail(
            ww["meters"], ww["frischwasser_per_m3"], ww["abwasser_per_m3"],
            ww["heizenergie_per_m3"], ww["num_tenants"], ww["bill_days"],
            ww["eff_days"], ww["prepay_monthly"], ww.get("is_pauschale", False))
    if body.heizung:
        h = body.heizung
        result["heizung"] = heizung_calc_detail(
            h["meters"], h["num_tenants"], h["bill_days"],
            h["eff_days"], h["prepay_monthly"], h.get("is_pauschale", False))
    if body.bk:
        bk = body.bk
        from datetime import date as _date
        bk_start = _date.fromisoformat(bk["bk_start"])
        bk_end = _date.fromisoformat(bk["bk_end"])
        ct, pc, lp, nach = betriebskosten_calc(
            bk["cost_flat"], bk["tenants"], bk["months"], bk_start, bk_end,
            bk.get("limit_per_month", 206))
        result["bk"] = {"cost_per_tenant": round(float(ct), 2),
                        "period_cost": round(float(pc), 2),
                        "limit_period": round(float(lp), 2),
                        "nach": round(float(nach), 2)}
    return result


# ── Nebenkostenabrechnung PDF ─────────────────────────────────────────────────

class NKRequest(BaseModel):
    tenant: str
    address: str
    gender: str = "diverse"
    contract_id: Optional[int] = None
    strom: Optional[Any] = None
    gas: Optional[Any] = None
    water: Optional[Any] = None
    warmwater: Optional[Any] = None
    heizung: Optional[Any] = None
    bk: Optional[Any] = None
    extra: Optional[Any] = None
    kaution_info: Optional[Any] = None
    landlord_info: Optional[Any] = None


@router.post("/nebenkostenabrechnung/pdf")
def nebenkostenabrechnung_pdf(body: NKRequest):
    from pdfgen import invoice_pdf
    # Co-tenants in the contract appear in the salutation/address block
    co_tenants = None
    if body.contract_id:
        rows = fetch("SELECT name, gender FROM co_tenants WHERE contract_id=? AND in_contract=1 ORDER BY id",
                     (body.contract_id,))
        co_tenants = [{"name": r[0], "gender": r[1]} for r in rows] or None
    # invoice_pdf writes to disk and returns the file path
    path = invoice_pdf(
        tenant=body.tenant, address=body.address,
        landlord_name=_landlord_name(), gender=body.gender,
        signature_path=_sig(), strom=body.strom, gas=body.gas,
        water=body.water, warmwater=body.warmwater, heizung=body.heizung,
        bk=body.bk, extra=body.extra, kaution_info=body.kaution_info,
        landlord_info=body.landlord_info, co_tenants=co_tenants,
    )
    pdf_bytes = Path(path).read_bytes()
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="Nebenkostenabrechnung.pdf"'})


# ── Mahnung ───────────────────────────────────────────────────────────────────

class MahnungRequest(BaseModel):
    tenant_name: str
    address: str
    amount_due: float
    contract_id: Optional[int] = None


@router.post("/mahnung/pdf")
def mahnung_pdf(body: MahnungRequest):
    from pdfgen import generate_mahnung
    from db import get_tenant_gender
    gender = get_tenant_gender(body.tenant_name)
    # Fetch co-tenants (in_contract only) to mirror the Streamlit flow
    co_tenants = None
    if body.contract_id:
        rows = fetch("SELECT name, gender FROM co_tenants WHERE contract_id=? AND in_contract=1 ORDER BY id",
                     (body.contract_id,))
        co_tenants = [{"name": r[0], "gender": r[1]} for r in rows] or None
    path = generate_mahnung(
        body.tenant_name, body.amount_due, body.address,
        gender=gender, signature_path=_sig(), co_tenants=co_tenants,
    )
    pdf_bytes = Path(path).read_bytes()
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="Mahnung.pdf"'})


# ── Payment Reminders ─────────────────────────────────────────────────────────

@router.get("/payment-reminders")
def payment_reminders():
    from logic import detect_overdue
    overdue = detect_overdue(months_back=12)
    # Enrich with property name and currency
    result = []
    for item in overdue:
        meta = fetch("""
            SELECT p.name, COALESCE(c.currency,'EUR')
            FROM contracts c
            JOIN apartments a ON a.id=c.apartment_id
            JOIN properties p ON p.id=a.property_id
            WHERE c.id=?
        """, (item["contract_id"],))
        prop_name = meta[0][0] if meta else ""
        currency = meta[0][1] if meta else "EUR"
        result.append({
            "contract_id":    item["contract_id"],
            "tenant_name":    item["tenant"],
            "tenant_email":   item.get("email", ""),
            "apartment_name": item["apartment"],
            "property_name":  prop_name,
            "months_due":     len(item["overdue_months"]),
            "amount_due":     round(float(item["total_due"]), 2),
            "currency":       currency,
            "overdue_months": item["overdue_months"],
        })
    return result


class ReminderIn(BaseModel):
    contract_id: int
    sent_date: str
    months_due: str
    amount_due: float
    channel: str = "manual"
    note: Optional[str] = None


class ReminderOut(BaseModel):
    id: int
    contract_id: int
    sent_date: str
    months_due: str
    amount_due: float
    channel: str
    note: Optional[str] = None


@router.get("/reminders/history")
def reminder_history():
    rows = fetch("""
        SELECT r.id, t.name, a.name, r.sent_date, r.months_due,
               r.amount_due, r.channel, r.note
        FROM reminders r
        JOIN contracts c ON r.contract_id = c.id
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        ORDER BY r.sent_date DESC
        LIMIT 200
    """)
    return [{"id": r[0], "tenant_name": r[1], "apartment_name": r[2],
             "sent_date": r[3], "months_due": r[4], "amount_due": float(r[5]),
             "channel": r[6], "note": r[7]} for r in rows]


@router.get("/reminders")
def list_reminders(contract_id: int | None = None):
    if contract_id:
        rows = fetch("""
            SELECT r.id, r.contract_id, r.sent_date, r.months_due, r.amount_due, r.channel, r.note
            FROM reminders r WHERE r.contract_id=? ORDER BY r.sent_date DESC
        """, (contract_id,))
    else:
        rows = fetch("""
            SELECT r.id, r.contract_id, r.sent_date, r.months_due, r.amount_due, r.channel, r.note
            FROM reminders r ORDER BY r.sent_date DESC LIMIT 100
        """)
    return [{"id": r[0], "contract_id": r[1], "sent_date": r[2],
             "months_due": r[3], "amount_due": float(r[4]),
             "channel": r[5], "note": r[6]} for r in rows]


@router.post("/reminders", status_code=201)
def create_reminder(body: ReminderIn):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO reminders (contract_id,sent_date,months_due,amount_due,channel,note)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (body.contract_id, body.sent_date, body.months_due,
              body.amount_due, body.channel, body.note))
        new_id = c.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    return {"id": new_id, "contract_id": body.contract_id, "sent_date": body.sent_date,
            "months_due": body.months_due, "amount_due": body.amount_due,
            "channel": body.channel, "note": body.note}
