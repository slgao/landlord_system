"""Nebenkostenabrechnungen sent to tenants, and what is still open on them.

A settlement records the result. What settles it is either money — payments
of kind 'nk_settlement' linked to it — or part of the deposit kept back: a
kaution_deductions row pointing at it through reference_type/reference_id.
Open/partial/settled is derived from both, never stored, so it cannot
disagree with them.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, model_validator

from auth import require_auth
from api.schemas.common import IsoDate, OptIsoDate
from db import execute, execute_returning, fetch
import nk_settlement_logic as logic

router = APIRouter(prefix="/nk-settlements", tags=["NK settlements"])

# An Abrechnung PDF is tens of kilobytes; this only stops an accident.
_MAX_PDF_BYTES = 5 * 1024 * 1024

# How a Kaution deduction points at the settlement it pays (the columns were
# on kaution_deductions from the start), and the category a Nachzahlung kept
# from the deposit is booked under. See kaution_rules.
from kaution_rules import NK_CATEGORY, NK_REF_TYPE as REF_TYPE



class NKSettlementIn(BaseModel):
    contract_id: int
    period_start: IsoDate
    period_end: IsoDate
    # Signed from the landlord's side: + Nachzahlung owed by the tenant,
    # − Guthaben owed to the tenant.
    amount: float
    issued_date: OptIsoDate = None
    note: Optional[str] = None
    # Create only: a Kaution deduction that already settled this Abrechnung.
    kaution_deduction_id: Optional[int] = None
    # The provider bills (expenses with a utility) this Abrechnung passes on.
    # One or several — a combined Abrechnung covers them all. On update,
    # None leaves the links as they are; a list replaces them.
    bill_ids: Optional[list[int]] = None

    @model_validator(mode="after")
    def _period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must not be before period_start")
        return self


class NKSettlementOut(BaseModel):
    id: int
    contract_id: int
    tenant_name: Optional[str] = None
    apartment_name: Optional[str] = None
    property_name: Optional[str] = None
    period_start: str
    period_end: str
    amount: float
    issued_date: Optional[str] = None
    note: Optional[str] = None
    has_pdf: bool = False
    paid: float = 0.0                 # payments + deposit kept back
    paid_from_kaution: float = 0.0
    # What the deposit still holds for this contract, when it can be used:
    # None once it has been returned, when there is none, or when it is not
    # held in EUR.
    kaution_available: Optional[float] = None
    kaution_deductions: list[dict] = []
    bills: list[dict] = []
    open: float = 0.0
    status: str                       # 'open' | 'partial' | 'settled'
    deadline: Optional[str] = None    # §556 Abs. 3 BGB
    # Whether it went out in time. None until an issue date is recorded.
    issued_on_time: Optional[bool] = None


class PendingAbrechnungOut(BaseModel):
    contract_id: int
    tenant_name: Optional[str] = None
    apartment_name: Optional[str] = None
    property_name: Optional[str] = None
    year: int
    period_start: str
    period_end: str
    deadline: str
    days_remaining: int
    level: str                        # 'due' | 'missed'
    # Nebenkosten already kept from this tenancy's deposit and not yet tied to
    # a settlement — most likely what settled this year. Recording the
    # settlement from one clears the reminder.
    deposit_deductions: list[dict] = []


# Deposit still held: the agreed amount less what was already deducted or
# paid back — the same figure the Kautionsverrechnung in the PDF uses.
_KAUTION_HELD = """
    CASE WHEN c.kaution_amount IS NULL
           OR COALESCE(c.kaution_currency, 'EUR') <> 'EUR'
           OR COALESCE(c.kaution_returned_date, '') NOT IN ('', 'None')
         THEN NULL
         ELSE c.kaution_amount
              - COALESCE((SELECT SUM(kd.amount) FROM kaution_deductions kd
                          WHERE kd.contract_id = c.id), 0)
              - COALESCE((SELECT SUM(kr.amount) FROM kaution_returns kr
                          WHERE kr.contract_id = c.id), 0)
    END
"""

_SELECT = f"""
    SELECT s.id, s.contract_id, t.name, a.name, p.name,
           s.period_start, s.period_end, s.amount, s.issued_date, s.note,
           s.pdf IS NOT NULL,
           COALESCE((SELECT SUM(pm.amount) FROM payments pm
                     WHERE pm.settlement_id = s.id), 0),
           COALESCE((SELECT SUM(d.amount) FROM kaution_deductions d
                     WHERE d.reference_type = '{REF_TYPE}' AND d.reference_id = s.id), 0),
           {_KAUTION_HELD}
    FROM nk_settlements s
    JOIN contracts  c ON c.id = s.contract_id
    JOIN tenants    t ON t.id = c.tenant_id
    JOIN apartments a ON a.id = c.apartment_id
    JOIN properties p ON p.id = a.property_id
"""


def _clean(v):
    return None if v is None or str(v) == "None" else str(v)


def _row(r, deductions=None, bills=None) -> NKSettlementOut:
    paid = float(r[11]) + float(r[12])
    open_, status = logic.settlement_state(r[7], paid)
    period_end = logic._parse(r[6])
    deadline = logic.abrechnung_deadline(period_end) if period_end else None
    issued = logic._parse(r[8])
    return NKSettlementOut(
        id=r[0], contract_id=r[1], tenant_name=r[2], apartment_name=r[3],
        property_name=r[4], period_start=r[5], period_end=r[6],
        amount=float(r[7]), issued_date=_clean(r[8]), note=r[9],
        has_pdf=bool(r[10]), paid=round(paid, 2), open=open_,
        paid_from_kaution=round(float(r[12]), 2),
        kaution_available=round(float(r[13]), 2) if r[13] is not None else None,
        kaution_deductions=deductions or [],
        bills=bills or [],
        status=status, deadline=str(deadline) if deadline else None,
        issued_on_time=(issued <= deadline) if (issued and deadline) else None,
    )


def _own_contract(contract_id: int, owner: int) -> None:
    if not fetch("SELECT id FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner)):
        raise HTTPException(404, "Contract not found")


def _own_settlement(settlement_id: int, owner: int) -> None:
    if not fetch("SELECT id FROM nk_settlements WHERE id=? AND owner_id=?",
                 (settlement_id, owner)):
        raise HTTPException(404, "Settlement not found")


def _linked_deductions(settlement_ids, owner) -> dict[int, list[dict]]:
    if not settlement_ids:
        return {}
    marks = ",".join("?" * len(settlement_ids))
    out: dict[int, list[dict]] = {}
    for sid, did, d, amt in fetch(
            f"SELECT reference_id, id, date, amount FROM kaution_deductions "
            f"WHERE reference_type = '{REF_TYPE}' AND owner_id = ? "
            f"AND reference_id IN ({marks}) ORDER BY date, id",
            (owner, *settlement_ids)):
        out.setdefault(sid, []).append({"id": did, "date": d, "amount": float(amt)})
    return out


def _linked_bills(settlement_ids, owner) -> dict[int, list[dict]]:
    if not settlement_ids:
        return {}
    marks = ",".join("?" * len(settlement_ids))
    out: dict[int, list[dict]] = {}
    for sid, *b in fetch(
            f"SELECT l.settlement_id, e.id, e.utility, e.vendor, e.period_start, e.period_end, "
            f"e.bill_total, e.amount, COALESCE(e.tenant_settled, 0) "
            f"FROM nk_settlement_bills l JOIN expenses e ON e.id = l.expense_id "
            f"WHERE l.owner_id = ? AND l.settlement_id IN ({marks}) ORDER BY e.period_start, e.id",
            (owner, *settlement_ids)):
        out.setdefault(sid, []).append(_bill_brief(b))
    return out


def _bill_brief(b) -> dict:
    eid, utility, vendor, ps, pe, total, amount, settled = b
    return {"id": eid, "utility": utility, "vendor": _clean(vendor),
            "period_start": _clean(ps), "period_end": _clean(pe),
            "bill_total": float(total) if total is not None else None,
            "amount": float(amount), "tenant_settled": bool(settled)}


def _rows(rows, owner) -> list[NKSettlementOut]:
    ids = [r[0] for r in rows]
    linked = _linked_deductions(ids, owner)
    bills = _linked_bills(ids, owner)
    return [_row(r, linked.get(r[0]), bills.get(r[0])) for r in rows]


def _check_bills(contract_id: int, bill_ids: list[int], owner: int) -> list[int]:
    """The bills, checked: each yours, a provider bill, and for the flat the
    tenant rents — a bill of another property cannot be passed on to them.
    Run before writing anything, so a refused bill leaves nothing behind."""
    bill_ids = sorted(set(bill_ids))
    if bill_ids:
        marks = ",".join("?" * len(bill_ids))
        ok = {r[0] for r in fetch(f"""
            SELECT e.id FROM expenses e
            JOIN apartments a ON a.property_id = e.property_id
            JOIN contracts c ON c.apartment_id = a.id
            WHERE c.id = ? AND e.owner_id = ? AND e.utility IS NOT NULL AND e.id IN ({marks})
        """, (contract_id, owner, *bill_ids))}
        bad = [b for b in bill_ids if b not in ok]
        if bad:
            raise HTTPException(409, "These bills are not provider bills of this tenant's "
                                     f"property: {', '.join(map(str, bad))}")
    return bill_ids


def _set_bills(settlement_id: int, bill_ids: list[int], owner: int) -> None:
    """Replace the bills an Abrechnung covers (already checked)."""
    execute("DELETE FROM nk_settlement_bills WHERE settlement_id=? AND owner_id=?",
            (settlement_id, owner))
    for b in bill_ids:
        execute("INSERT INTO nk_settlement_bills (settlement_id, expense_id, owner_id) "
                "VALUES (?,?,?)", (settlement_id, b, owner))


def _one(settlement_id: int, owner: int) -> NKSettlementOut:
    rows = fetch(f"{_SELECT} WHERE s.id=? AND s.owner_id=?", (settlement_id, owner))
    if not rows:
        raise HTTPException(404, "Settlement not found")
    return _rows(rows, owner)[0]


def _tenancy(contract_id: int, owner: int):
    rows = fetch("SELECT tenant_id, apartment_id FROM contracts WHERE id=? AND owner_id=?",
                 (contract_id, owner))
    return rows[0] if rows else None


def _linkable_deduction(deduction_id: int, contract_id: int, owner: int, room: float):
    """The deduction, checked: yours, not already paying another settlement,
    from the same tenant and flat, and not more than is left to settle."""
    rows = fetch("SELECT contract_id, amount, reference_type, reference_id "
                 "FROM kaution_deductions WHERE id=? AND owner_id=?", (deduction_id, owner))
    if not rows:
        raise HTTPException(404, "Kaution deduction not found")
    d_contract, d_amount, ref_type, ref_id = rows[0]
    if ref_type == REF_TYPE and ref_id is not None:
        raise HTTPException(409, "That deduction already settles another Abrechnung")
    if _tenancy(d_contract, owner) != _tenancy(contract_id, owner):
        raise HTTPException(409, "That deduction belongs to a different tenant or flat")
    if float(d_amount) > room + 0.005:
        raise HTTPException(409, f"The deduction ({float(d_amount):.2f} €) is more than is "
                                 f"left to settle ({room:.2f} €)")
    return rows[0]


@router.get("/", response_model=list[NKSettlementOut])
def list_settlements(contract_id: int | None = None, owner: int = Depends(require_auth)):
    if contract_id:
        rows = fetch(f"{_SELECT} WHERE s.contract_id=? AND s.owner_id=? "
                     "ORDER BY s.period_end DESC, s.id DESC", (contract_id, owner))
    else:
        rows = fetch(f"{_SELECT} WHERE s.owner_id=? ORDER BY s.period_end DESC, s.id DESC",
                     (owner,))
    return _rows(rows, owner)


@router.get("/pending", response_model=list[PendingAbrechnungOut])
def pending(owner: int = Depends(require_auth)):
    """Tenancies whose Abrechnung for a finished year is not recorded yet,
    with the §556 deadline. See nk_settlement_logic.pending_abrechnungen."""
    contracts = fetch("""
        SELECT c.id, c.tenant_id, c.apartment_id, c.start_date, c.end_date,
               c.nebenkosten_vorauszahlung, c.nk_mode, t.name, a.name, p.name
        FROM contracts c
        JOIN tenants    t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE c.owner_id = ?
    """, (owner,))
    settlements = fetch("SELECT contract_id, period_start, period_end FROM nk_settlements "
                        "WHERE owner_id=?", (owner,))
    names = {r[0]: (r[7], r[8], r[9]) for r in contracts}
    tenancy = {r[0]: (r[1], r[2]) for r in contracts}
    due = logic.pending_abrechnungen([r[:7] for r in contracts], settlements, date.today())

    # Unlinked NK deductions per tenancy (a follow-on contract is the same one).
    by_tenancy: dict[tuple, list[dict]] = {}
    if due:
        for did, cid, d_date, amount in fetch(f"""
            SELECT d.id, d.contract_id, d.date, d.amount FROM kaution_deductions d
            WHERE d.owner_id = ? AND {_UNLINKED_NK_DEDUCTION}
            ORDER BY d.date, d.id
        """, (owner, NK_CATEGORY)):
            if cid in tenancy:
                by_tenancy.setdefault(tenancy[cid], []).append(
                    {"id": did, "date": _clean(d_date), "amount": float(amount)})

    out = []
    for d in due:
        # A deduction can only settle a year that had begun by the time the
        # deposit was kept.
        candidates = [x for x in by_tenancy.get(tenancy[d["contract_id"]], [])
                      if x["date"] and x["date"] >= d["period_start"]]
        out.append(PendingAbrechnungOut(
            **d, tenant_name=names[d["contract_id"]][0],
            apartment_name=names[d["contract_id"]][1],
            property_name=names[d["contract_id"]][2],
            deposit_deductions=candidates))
    return out


# A Kaution deduction for Nebenkosten that no settlement points at yet: in the
# NK category, or with a reason that says Nebenkosten. Alias `d`, one `?` for
# NK_CATEGORY. Shared by the import card and the reminder rows.
_UNLINKED_NK_DEDUCTION = f"""
    COALESCE(d.reference_type, '') <> '{REF_TYPE}'
    AND (d.category = ?
         OR d.reason ILIKE '%nebenkosten%' OR d.reason ILIKE '%betriebskosten%'
         OR d.reason ILIKE '%nk-abrechnung%' OR d.reason ILIKE '%nk abrechnung%')
"""


class UnlinkedKautionOut(BaseModel):
    id: int
    contract_id: int
    tenant_name: Optional[str] = None
    apartment_name: Optional[str] = None
    property_name: Optional[str] = None
    date: Optional[str] = None
    amount: float
    category: Optional[str] = None
    reason: Optional[str] = None
    # Open Nachzahlungen of the same tenant and flat it could settle.
    candidates: list[int] = []


@router.get("/unlinked-kaution", response_model=list[UnlinkedKautionOut])
def unlinked_kaution(owner: int = Depends(require_auth)):
    """Nebenkosten already settled from a deposit, before this page knew
    about deposits: deductions in the NK category, or whose reason says
    Nebenkosten, that no settlement points at yet."""
    rows = fetch(f"""
        SELECT d.id, d.contract_id, t.name, a.name, p.name, d.date, d.amount,
               d.category, d.reason, c.tenant_id, c.apartment_id
        FROM kaution_deductions d
        JOIN contracts  c ON c.id = d.contract_id
        JOIN tenants    t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE d.owner_id = ? AND {_UNLINKED_NK_DEDUCTION}
        ORDER BY d.date DESC, d.id DESC
    """, (owner, NK_CATEGORY))
    open_by_tenancy: dict[tuple, list[int]] = {}
    for r in fetch(f"""
        SELECT c.tenant_id, c.apartment_id, s.id, s.amount,
               COALESCE((SELECT SUM(pm.amount) FROM payments pm WHERE pm.settlement_id = s.id), 0)
             + COALESCE((SELECT SUM(d.amount) FROM kaution_deductions d
                         WHERE d.reference_type = '{REF_TYPE}' AND d.reference_id = s.id), 0)
        FROM nk_settlements s JOIN contracts c ON c.id = s.contract_id
        WHERE s.owner_id = ? AND s.amount > 0
        ORDER BY s.period_end DESC
    """, (owner,)):
        if float(r[3]) - float(r[4]) > 0.005:
            open_by_tenancy.setdefault((r[0], r[1]), []).append(r[2])
    return [UnlinkedKautionOut(
        id=r[0], contract_id=r[1], tenant_name=r[2], apartment_name=r[3],
        property_name=r[4], date=_clean(r[5]), amount=float(r[6]), category=r[7],
        reason=r[8], candidates=open_by_tenancy.get((r[9], r[10]), []))
        for r in rows]


class BillOut(BaseModel):
    id: int
    property_id: int
    property_name: Optional[str] = None
    utility: str
    vendor: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    bill_total: Optional[float] = None
    amount: float                      # paid beyond the Abschläge (− Guthaben)
    expense_date: str
    category: str
    note: Optional[str] = None
    has_pdf: bool = False
    tenant_settled: bool = False       # your decision, see the migration
    settlements: list[dict] = []       # tenant Abrechnungen that cover it


class BillSettledIn(BaseModel):
    tenant_settled: bool


@router.get("/bills", response_model=list[BillOut])
def list_bills(property_id: Optional[int] = None, contract_id: Optional[int] = None,
               owner: int = Depends(require_auth)):
    """Provider bills — expenses with a utility — and the tenant Abrechnungen
    each one has been passed on in. `contract_id` narrows to the property that
    tenant rents in: the bills an Abrechnung for them can cover."""
    where, params = "e.owner_id = ? AND e.utility IS NOT NULL", [owner]
    if property_id:
        where += " AND e.property_id = ?"
        params.append(property_id)
    if contract_id:
        where += (" AND e.property_id = (SELECT a.property_id FROM contracts c "
                  "JOIN apartments a ON a.id = c.apartment_id WHERE c.id = ? AND c.owner_id = ?)")
        params += [contract_id, owner]
    rows = fetch(f"""
        SELECT e.id, e.property_id, p.name, e.utility, e.vendor, e.period_start,
               e.period_end, e.bill_total, e.amount, e.expense_date, e.category, e.note,
               e.pdf IS NOT NULL, COALESCE(e.tenant_settled, 0)
        FROM expenses e JOIN properties p ON p.id = e.property_id
        WHERE {where}
        ORDER BY COALESCE(e.period_end, e.expense_date) DESC, e.id DESC
    """, tuple(params))
    covered: dict[int, list[dict]] = {}
    if rows:
        marks = ",".join("?" * len(rows))
        for eid, sid, tname, ps, pe in fetch(f"""
            SELECT l.expense_id, s.id, t.name, s.period_start, s.period_end
            FROM nk_settlement_bills l
            JOIN nk_settlements s ON s.id = l.settlement_id
            JOIN contracts c ON c.id = s.contract_id
            JOIN tenants t ON t.id = c.tenant_id
            WHERE l.owner_id = ? AND l.expense_id IN ({marks})
            ORDER BY t.name
        """, (owner, *[r[0] for r in rows])):
            covered.setdefault(eid, []).append(
                {"id": sid, "tenant_name": tname, "period_start": ps, "period_end": pe})
    return [BillOut(
        id=r[0], property_id=r[1], property_name=r[2], utility=r[3], vendor=_clean(r[4]),
        period_start=_clean(r[5]), period_end=_clean(r[6]),
        bill_total=float(r[7]) if r[7] is not None else None, amount=float(r[8]),
        expense_date=r[9], category=r[10], note=_clean(r[11]), has_pdf=bool(r[12]),
        tenant_settled=bool(r[13]), settlements=covered.get(r[0], []))
        for r in rows]


@router.put("/bills/{expense_id}/settled", response_model=dict)
def set_bill_settled(expense_id: int, body: BillSettledIn, owner: int = Depends(require_auth)):
    """Mark a bill as fully passed on to the tenants, or open again."""
    if not fetch("SELECT id FROM expenses WHERE id=? AND owner_id=? AND utility IS NOT NULL",
                 (expense_id, owner)):
        raise HTTPException(404, "Provider bill not found")
    execute("UPDATE expenses SET tenant_settled=? WHERE id=? AND owner_id=?",
            (int(body.tenant_settled), expense_id, owner))
    return {"id": expense_id, "tenant_settled": body.tenant_settled}


@router.post("/", response_model=NKSettlementOut, status_code=201)
def create_settlement(body: NKSettlementIn, owner: int = Depends(require_auth)):
    _own_contract(body.contract_id, owner)
    bill_ids = _check_bills(body.contract_id, body.bill_ids or [], owner)
    params = (body.contract_id, body.period_start, body.period_end, body.amount,
              body.issued_date, body.note or None, owner)
    insert = """
        INSERT INTO nk_settlements
            (contract_id, period_start, period_end, amount, issued_date, note, owner_id)
        VALUES (?,?,?,?,?,?,?) RETURNING id
    """
    if body.kaution_deduction_id is None:
        new_id = execute_returning(insert, params)[0][0]
    else:
        if body.amount <= 0:
            raise HTTPException(422, "Only a Nachzahlung can be settled from the deposit")
        _linkable_deduction(body.kaution_deduction_id, body.contract_id, owner, body.amount)
        # One statement, so a settlement never exists without the link it
        # was created for.
        new_id = execute_returning(f"""
            WITH s AS ({insert})
            UPDATE kaution_deductions
            SET reference_type = '{REF_TYPE}', reference_id = (SELECT id FROM s)
            WHERE id = ? AND owner_id = ?
            RETURNING reference_id
        """, (*params, body.kaution_deduction_id, owner))[0][0]
    if bill_ids:
        _set_bills(new_id, bill_ids, owner)
    return _one(new_id, owner)


class KautionLinkIn(BaseModel):
    deduction_id: int


class KautionSettleIn(BaseModel):
    date: IsoDate
    # Defaults to as much as the deposit covers of what is still open.
    amount: Optional[float] = None


@router.post("/{settlement_id}/kaution-links", response_model=NKSettlementOut)
def link_kaution(settlement_id: int, body: KautionLinkIn, owner: int = Depends(require_auth)):
    """Record that an existing deduction already paid this Abrechnung."""
    s = _one(settlement_id, owner)
    if s.amount <= 0:
        raise HTTPException(422, "Only a Nachzahlung can be settled from the deposit")
    _linkable_deduction(body.deduction_id, s.contract_id, owner, s.open)
    execute(f"UPDATE kaution_deductions SET reference_type='{REF_TYPE}', reference_id=? "
            "WHERE id=? AND owner_id=?", (settlement_id, body.deduction_id, owner))
    return _one(settlement_id, owner)


@router.delete("/{settlement_id}/kaution-links/{deduction_id}", response_model=NKSettlementOut)
def unlink_kaution(settlement_id: int, deduction_id: int, owner: int = Depends(require_auth)):
    """Undo a link. The deduction itself stays: the deposit was still kept."""
    _own_settlement(settlement_id, owner)
    execute(f"UPDATE kaution_deductions SET reference_type=NULL, reference_id=NULL "
            f"WHERE id=? AND owner_id=? AND reference_type='{REF_TYPE}' AND reference_id=?",
            (deduction_id, owner, settlement_id))
    return _one(settlement_id, owner)


@router.post("/{settlement_id}/settle-from-kaution", response_model=NKSettlementOut)
def settle_from_kaution(settlement_id: int, body: KautionSettleIn,
                        owner: int = Depends(require_auth)):
    """Keep part of the deposit for an open Nachzahlung: books the Kaution
    deduction, linked, so the deposit ledger and the settlement agree."""
    s = _one(settlement_id, owner)
    if s.amount <= 0:
        raise HTTPException(422, "A Guthaben is paid back, not taken from the deposit")
    if s.open <= 0.005:
        raise HTTPException(409, "Nothing is open on this settlement")
    if not s.kaution_available or s.kaution_available <= 0.005:
        raise HTTPException(409, "No deposit is held for this contract any more")
    most = round(min(s.open, s.kaution_available), 2)
    amount = most if body.amount is None else round(body.amount, 2)
    if amount <= 0 or amount > most + 0.005:
        raise HTTPException(422, f"Amount must be between 0 and {most:.2f} €")
    reason = (f"Nebenkostenabrechnung {logic._parse(s.period_start):%d.%m.%Y}"
              f"–{logic._parse(s.period_end):%d.%m.%Y}")
    execute(f"""
        INSERT INTO kaution_deductions
            (contract_id, date, amount, category, reason, reference_type, reference_id, owner_id)
        VALUES (?,?,?,?,?,'{REF_TYPE}',?,?)
    """, (s.contract_id, body.date, amount, NK_CATEGORY, reason, settlement_id, owner))
    return _one(settlement_id, owner)


@router.put("/{settlement_id}", response_model=NKSettlementOut)
def update_settlement(settlement_id: int, body: NKSettlementIn,
                      owner: int = Depends(require_auth)):
    _own_settlement(settlement_id, owner)
    _own_contract(body.contract_id, owner)
    # Payments already booked against it belong to the old contract; moving
    # the settlement would leave them pointing across tenancies.
    if fetch("SELECT 1 FROM payments WHERE settlement_id=? AND contract_id<>? LIMIT 1",
             (settlement_id, body.contract_id)):
        raise HTTPException(409, "Payments for another contract are linked to this "
                                 "settlement — remove them before moving it.")
    bill_ids = (_check_bills(body.contract_id, body.bill_ids, owner)
                if body.bill_ids is not None else None)
    linked = fetch(f"SELECT contract_id FROM kaution_deductions "
                   f"WHERE reference_type='{REF_TYPE}' AND reference_id=? AND owner_id=?",
                   (settlement_id, owner))
    if linked and body.amount <= 0:
        raise HTTPException(409, "Deposit deductions settle this Nachzahlung — unlink them "
                                 "before turning it into a Guthaben.")
    tenancy = _tenancy(body.contract_id, owner)
    if any(_tenancy(cid, owner) != tenancy for (cid,) in linked):
        raise HTTPException(409, "A deposit deduction of another tenant or flat is linked "
                                 "to this settlement — unlink it before moving it.")
    execute("""
        UPDATE nk_settlements
        SET contract_id=?, period_start=?, period_end=?, amount=?, issued_date=?, note=?
        WHERE id=? AND owner_id=?
    """, (body.contract_id, body.period_start, body.period_end, body.amount,
          body.issued_date, body.note or None, settlement_id, owner))
    if bill_ids is not None:
        _set_bills(settlement_id, bill_ids, owner)
    elif fetch("SELECT 1 FROM nk_settlements s JOIN contracts c ON c.id = s.contract_id "
               "JOIN apartments a ON a.id = c.apartment_id "
               "JOIN nk_settlement_bills l ON l.settlement_id = s.id "
               "JOIN expenses e ON e.id = l.expense_id "
               "WHERE s.id = ? AND e.property_id <> a.property_id LIMIT 1", (settlement_id,)):
        # Moved to a tenant of another property: its bills no longer apply.
        _set_bills(settlement_id, [], owner)
    return _one(settlement_id, owner)


@router.delete("/{settlement_id}", status_code=204)
def delete_settlement(settlement_id: int, owner: int = Depends(require_auth)):
    """Linked payments and deductions stay: the money moved, and the deposit
    was kept, whether or not the record does. Payments lose the link through
    ON DELETE SET NULL; a deduction's reference is polymorphic, so it has no
    foreign key and is cleared here."""
    _own_settlement(settlement_id, owner)
    execute(f"UPDATE kaution_deductions SET reference_type=NULL, reference_id=NULL "
            f"WHERE reference_type='{REF_TYPE}' AND reference_id=? AND owner_id=?",
            (settlement_id, owner))
    execute("DELETE FROM nk_settlements WHERE id=? AND owner_id=?", (settlement_id, owner))


@router.put("/{settlement_id}/pdf", response_model=NKSettlementOut)
async def upload_pdf(settlement_id: int, file: UploadFile = File(...),
                     owner: int = Depends(require_auth)):
    data = await file.read(_MAX_PDF_BYTES + 1)
    if len(data) > _MAX_PDF_BYTES:
        raise HTTPException(413, "The PDF is larger than 5 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "That file is not a PDF")
    from starlette.concurrency import run_in_threadpool

    def _store():
        _own_settlement(settlement_id, owner)
        execute("UPDATE nk_settlements SET pdf=? WHERE id=? AND owner_id=?",
                (data, settlement_id, owner))
        return _one(settlement_id, owner)
    return await run_in_threadpool(_store)


@router.get("/{settlement_id}/pdf")
def download_pdf(settlement_id: int, owner: int = Depends(require_auth)):
    rows = fetch("SELECT pdf, period_end FROM nk_settlements WHERE id=? AND owner_id=?",
                 (settlement_id, owner))
    if not rows or rows[0][0] is None:
        raise HTTPException(404, "No PDF stored for this settlement")
    return Response(content=bytes(rows[0][0]), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'inline; filename="Nebenkostenabrechnung_{rows[0][1]}.pdf"'})
