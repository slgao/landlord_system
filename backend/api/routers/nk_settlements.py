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
from db import execute, execute_returning, fetch, fetch_bundle
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

_SETTLEMENT_COLS = f"""
           s.id, s.contract_id, t.name, a.name, p.name,
           s.period_start, s.period_end, s.amount, s.issued_date, s.note,
           s.pdf IS NOT NULL,
           COALESCE((SELECT SUM(pm.amount) FROM payments pm
                     WHERE pm.settlement_id = s.id), 0),
           COALESCE((SELECT SUM(d.amount) FROM kaution_deductions d
                     WHERE d.reference_type = '{REF_TYPE}' AND d.reference_id = s.id), 0),
           {_KAUTION_HELD},
           -- Deposit kept and bills covered come back with the row rather than
           -- as two more round trips; the database is 40 ms away.
           COALESCE((SELECT json_agg(json_build_object('id', d.id, 'date', d.date,
                                                       'amount', d.amount)
                                     ORDER BY d.date, d.id)
                     FROM kaution_deductions d
                     WHERE d.reference_type = '{REF_TYPE}' AND d.reference_id = s.id), '[]'),
           COALESCE((SELECT json_agg(json_build_object(
                         'id', e.id, 'utility', e.utility, 'vendor', e.vendor,
                         'period_start', e.period_start, 'period_end', e.period_end,
                         'bill_total', e.bill_total, 'amount', e.amount,
                         'tenant_settled', COALESCE(e.tenant_settled, 0) = 1)
                         ORDER BY e.period_start, e.id)
                     FROM nk_settlement_bills l JOIN expenses e ON e.id = l.expense_id
                     WHERE l.settlement_id = s.id), '[]')
"""

_SETTLEMENT_FROM = """
    FROM nk_settlements s
    JOIN contracts  c ON c.id = s.contract_id
    JOIN tenants    t ON t.id = c.tenant_id
    JOIN apartments a ON a.id = c.apartment_id
    JOIN properties p ON p.id = a.property_id
"""

_SELECT = f"SELECT {_SETTLEMENT_COLS} {_SETTLEMENT_FROM}"


def _part(name: str, cols: str, rest: str, params) -> tuple:
    """One query of a bundle: the same SQL as the plain version, with its
    columns wrapped so the rows come back positional (see db.fetch_bundle)."""
    return (name, f"SELECT json_build_array({cols}) {rest}", params)


def _clean(v):
    return None if v is None or str(v) == "None" else str(v)


def _row(r) -> NKSettlementOut:
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
        kaution_deductions=r[14],
        bills=r[15],
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


def _rows(rows, owner) -> list[NKSettlementOut]:
    return [_row(r) for r in rows]


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
    """Replace the bills an Abrechnung covers (already checked). One statement:
    the old links never disappear without the new ones arriving, and a
    settlement covering six bills costs one round trip, not seven."""
    if not bill_ids:
        execute("DELETE FROM nk_settlement_bills WHERE settlement_id=? AND owner_id=?",
                (settlement_id, owner))
        return
    execute("""
        WITH cleared AS (
            DELETE FROM nk_settlement_bills WHERE settlement_id=? AND owner_id=?
        )
        INSERT INTO nk_settlement_bills (settlement_id, expense_id, owner_id)
        SELECT ?, e, ? FROM unnest(?::int[]) AS e
    """, (settlement_id, owner, settlement_id, owner, bill_ids))


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
    return _rows(fetch_bundle([_q_settlements(owner, contract_id)])["settlements"], owner)


def _q_settlements(owner, contract_id=None):
    where = "WHERE s.contract_id=? AND s.owner_id=?" if contract_id else "WHERE s.owner_id=?"
    params = (contract_id, owner) if contract_id else (owner,)
    return _part("settlements", _SETTLEMENT_COLS,
                 f"{_SETTLEMENT_FROM} {where} ORDER BY s.period_end DESC, s.id DESC", params)


def _q_pending_contracts(owner):
    return _part("pending_contracts",
                 """c.id, c.tenant_id, c.apartment_id, c.start_date, c.end_date,
                    c.nebenkosten_vorauszahlung, c.nk_mode, t.name, a.name, p.name""",
                 """FROM contracts c
                    JOIN tenants    t ON t.id = c.tenant_id
                    JOIN apartments a ON a.id = c.apartment_id
                    JOIN properties p ON p.id = a.property_id
                    WHERE c.owner_id = ?""", (owner,))


def _q_pending_rows(owner):
    """Recorded settlements and unlinked NK deductions, tagged apart."""
    return ("pending_rows", f"""
        SELECT json_build_array(0, contract_id, period_start, period_end, NULL, NULL, id)
        FROM nk_settlements WHERE owner_id = ?
        UNION ALL
        SELECT json_build_array(1, d.contract_id, NULL, NULL, d.date, d.amount, d.id)
        FROM kaution_deductions d WHERE d.owner_id = ? AND {_UNLINKED_NK_DEDUCTION}
    """, (owner, owner, NK_CATEGORY))


def _pending_from(contracts, rows, today) -> list[PendingAbrechnungOut]:
    settlements = [(r[1], r[2], r[3]) for r in rows if r[0] == 0]
    deductions = [(r[1], r[4], r[5], r[6]) for r in rows if r[0] == 1]
    names = {r[0]: (r[7], r[8], r[9]) for r in contracts}
    tenancy = {r[0]: (r[1], r[2]) for r in contracts}
    due = logic.pending_abrechnungen([r[:7] for r in contracts], settlements, today)

    by_tenancy: dict[tuple, list[dict]] = {}
    for cid, d_date, amount, did in deductions:
        if cid in tenancy:
            by_tenancy.setdefault(tenancy[cid], []).append(
                {"id": did, "date": _clean(d_date), "amount": float(amount)})

    out = []
    for d in due:
        # A deduction can only settle a year that had begun by the time the
        # deposit was kept.
        candidates = sorted(
            (x for x in by_tenancy.get(tenancy[d["contract_id"]], [])
             if x["date"] and x["date"] >= d["period_start"]),
            key=lambda x: (x["date"], x["id"]))
        out.append(PendingAbrechnungOut(
            **d, tenant_name=names[d["contract_id"]][0],
            apartment_name=names[d["contract_id"]][1],
            property_name=names[d["contract_id"]][2],
            deposit_deductions=candidates))
    return out


@router.get("/pending", response_model=list[PendingAbrechnungOut])
def pending(owner: int = Depends(require_auth)):
    """Tenancies whose Abrechnung for a finished year is not recorded yet,
    with the §556 deadline. See nk_settlement_logic.pending_abrechnungen."""
    loaded = fetch_bundle([_q_pending_contracts(owner), _q_pending_rows(owner)])
    return _pending_from(loaded["pending_contracts"], loaded["pending_rows"], date.today())


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
    loaded = fetch_bundle([_q_unlinked(owner), _q_open_settlements(owner)])
    return _unlinked_from(loaded["unlinked"], loaded["open_settlements"])


def _q_unlinked(owner):
    return _part("unlinked",
                 """d.id, d.contract_id, t.name, a.name, p.name, d.date, d.amount,
                    d.category, d.reason, c.tenant_id, c.apartment_id""",
                 f"""FROM kaution_deductions d
                     JOIN contracts  c ON c.id = d.contract_id
                     JOIN tenants    t ON t.id = c.tenant_id
                     JOIN apartments a ON a.id = c.apartment_id
                     JOIN properties p ON p.id = a.property_id
                     WHERE d.owner_id = ? AND {_UNLINKED_NK_DEDUCTION}
                     ORDER BY d.date DESC, d.id DESC""", (owner, NK_CATEGORY))


def _q_open_settlements(owner):
    """Nachzahlungen with something still open, to match a deduction against."""
    return _part("open_settlements", f"""
                    c.tenant_id, c.apartment_id, s.id, s.amount,
                    COALESCE((SELECT SUM(pm.amount) FROM payments pm
                              WHERE pm.settlement_id = s.id), 0)
                  + COALESCE((SELECT SUM(d.amount) FROM kaution_deductions d
                              WHERE d.reference_type = '{REF_TYPE}'
                                AND d.reference_id = s.id), 0)""",
                 """FROM nk_settlements s JOIN contracts c ON c.id = s.contract_id
                    WHERE s.owner_id = ? AND s.amount > 0
                    ORDER BY s.period_end DESC""", (owner,))


def _unlinked_from(rows, open_rows) -> list[UnlinkedKautionOut]:
    open_by_tenancy: dict[tuple, list[int]] = {}
    for r in open_rows:
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


class BillCandidateOut(BaseModel):
    """An expense that is not a bill yet but reads like one."""
    id: int
    property_id: int
    property_name: Optional[str] = None
    expense_date: str
    amount: float
    category: str
    vendor: Optional[str] = None
    apartment_id: Optional[int] = None
    deductible: int = 1
    distribute_years: int = 1
    source_file: Optional[str] = None
    note: Optional[str] = None


@router.get("/bill-candidates", response_model=list[BillCandidateOut])
def bill_candidates(owner: int = Depends(require_auth)):
    """Expenses that could be turned into provider bills — the ones recorded
    before bills existed. Slim on purpose: the page only needs to list them
    in a dropdown, and the full expense list is 35 KB of notes."""
    return _candidates_from(fetch_bundle([_q_candidates(owner)])["candidates"])


def _q_candidates(owner):
    return _part("candidates",
                 """e.id, e.property_id, p.name, e.expense_date, e.amount, e.category,
                    e.vendor, e.apartment_id, e.deductible, e.distribute_years,
                    e.source_file, e.note""",
                 """FROM expenses e JOIN properties p ON p.id = e.property_id
                    WHERE e.owner_id = ? AND e.utility IS NULL
                      AND e.category IN ('Hausgeld', 'Versorgerabrechnung', 'Sonstige')
                    ORDER BY e.expense_date DESC, e.id DESC""", (owner,))


def _candidates_from(rows) -> list[BillCandidateOut]:
    return [BillCandidateOut(
        id=r[0], property_id=r[1], property_name=r[2], expense_date=r[3], amount=float(r[4]),
        category=r[5], vendor=_clean(r[6]), apartment_id=r[7], deductible=int(r[8] or 1),
        distribute_years=int(r[9] or 1), source_file=_clean(r[10]), note=_clean(r[11]))
        for r in rows]


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
    return _bills_from(fetch_bundle([_q_bills(where, tuple(params))])["bills"])


_BILL_COLS = """
    e.id, e.property_id, p.name, e.utility, e.vendor, e.period_start,
    e.period_end, e.bill_total, e.amount, e.expense_date, e.category, e.note,
    e.pdf IS NOT NULL, COALESCE(e.tenant_settled, 0),
    COALESCE((SELECT json_agg(json_build_object(
                  'id', s.id, 'tenant_name', t.name,
                  'period_start', s.period_start, 'period_end', s.period_end)
                  ORDER BY t.name)
              FROM nk_settlement_bills l
              JOIN nk_settlements s ON s.id = l.settlement_id
              JOIN contracts c ON c.id = s.contract_id
              JOIN tenants t ON t.id = c.tenant_id
              WHERE l.expense_id = e.id), '[]')
"""


def _q_bills(where: str, params: tuple):
    return _part("bills", _BILL_COLS,
                 f"""FROM expenses e JOIN properties p ON p.id = e.property_id
                     WHERE {where}
                     ORDER BY COALESCE(e.period_end, e.expense_date) DESC, e.id DESC""",
                 params)


def _bills_from(rows) -> list[BillOut]:
    return [BillOut(
        id=r[0], property_id=r[1], property_name=r[2], utility=r[3], vendor=_clean(r[4]),
        period_start=_clean(r[5]), period_end=_clean(r[6]),
        bill_total=float(r[7]) if r[7] is not None else None, amount=float(r[8]),
        expense_date=r[9], category=r[10], note=_clean(r[11]), has_pdf=bool(r[12]),
        tenant_settled=bool(r[13]), settlements=r[14])
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


class OverviewOut(BaseModel):
    settlements: list[NKSettlementOut] = []
    pending: list[PendingAbrechnungOut] = []
    unlinked_kaution: list[UnlinkedKautionOut] = []
    bills: list[BillOut] = []
    bill_candidates: list[BillCandidateOut] = []


@router.get("/overview", response_model=OverviewOut)
def overview(owner: int = Depends(require_auth)):
    """Everything the NK Settlements page shows, in one request. Five
    serialised requests over a 40 ms link cost more than the queries do."""
    loaded = fetch_bundle([
        _q_settlements(owner), _q_pending_contracts(owner), _q_pending_rows(owner),
        _q_unlinked(owner), _q_open_settlements(owner),
        _q_bills("e.owner_id = ? AND e.utility IS NOT NULL", (owner,)), _q_candidates(owner),
    ])
    return OverviewOut(
        settlements=_rows(loaded["settlements"], owner),
        pending=_pending_from(loaded["pending_contracts"], loaded["pending_rows"], date.today()),
        unlinked_kaution=_unlinked_from(loaded["unlinked"], loaded["open_settlements"]),
        bills=_bills_from(loaded["bills"]),
        bill_candidates=_candidates_from(loaded["candidates"]),
    )


class DashboardNKOut(BaseModel):
    pending: list[PendingAbrechnungOut] = []
    open_settlements: list[NKSettlementOut] = []


@router.get("/dashboard", response_model=DashboardNKOut)
def dashboard(days: int = 120, owner: int = Depends(require_auth)):
    """What the dashboard card shows, in one request instead of two: the
    Abrechnungen due soon or just missed, and the settlements still open."""
    loaded = fetch_bundle([
        _q_settlements(owner), _q_pending_contracts(owner), _q_pending_rows(owner),
    ])
    due = _pending_from(loaded["pending_contracts"], loaded["pending_rows"], date.today())
    return DashboardNKOut(
        pending=[p for p in due if p.days_remaining <= days],
        open_settlements=[s for s in _rows(loaded["settlements"], owner)
                          if s.status != "settled"],
    )


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
