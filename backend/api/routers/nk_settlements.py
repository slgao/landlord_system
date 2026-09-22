"""Nebenkostenabrechnungen sent to tenants, and what is still open on them.

A settlement records the result; the money is ordinary payments of kind
'nk_settlement' linked to it. Open/partial/settled is derived from those
payments, never stored, so it cannot disagree with them.
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


class NKSettlementIn(BaseModel):
    contract_id: int
    period_start: IsoDate
    period_end: IsoDate
    # Signed from the landlord's side: + Nachzahlung owed by the tenant,
    # − Guthaben owed to the tenant.
    amount: float
    issued_date: OptIsoDate = None
    note: Optional[str] = None

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
    paid: float = 0.0
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


_SELECT = """
    SELECT s.id, s.contract_id, t.name, a.name, p.name,
           s.period_start, s.period_end, s.amount, s.issued_date, s.note,
           s.pdf IS NOT NULL,
           COALESCE((SELECT SUM(pm.amount) FROM payments pm
                     WHERE pm.settlement_id = s.id), 0)
    FROM nk_settlements s
    JOIN contracts  c ON c.id = s.contract_id
    JOIN tenants    t ON t.id = c.tenant_id
    JOIN apartments a ON a.id = c.apartment_id
    JOIN properties p ON p.id = a.property_id
"""


def _clean(v):
    return None if v is None or str(v) == "None" else str(v)


def _row(r) -> NKSettlementOut:
    open_, status = logic.settlement_state(r[7], r[11])
    period_end = logic._parse(r[6])
    deadline = logic.abrechnung_deadline(period_end) if period_end else None
    issued = logic._parse(r[8])
    return NKSettlementOut(
        id=r[0], contract_id=r[1], tenant_name=r[2], apartment_name=r[3],
        property_name=r[4], period_start=r[5], period_end=r[6],
        amount=float(r[7]), issued_date=_clean(r[8]), note=r[9],
        has_pdf=bool(r[10]), paid=round(float(r[11]), 2), open=open_,
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


def _one(settlement_id: int, owner: int) -> NKSettlementOut:
    rows = fetch(f"{_SELECT} WHERE s.id=? AND s.owner_id=?", (settlement_id, owner))
    if not rows:
        raise HTTPException(404, "Settlement not found")
    return _row(rows[0])


@router.get("/", response_model=list[NKSettlementOut])
def list_settlements(contract_id: int | None = None, owner: int = Depends(require_auth)):
    if contract_id:
        rows = fetch(f"{_SELECT} WHERE s.contract_id=? AND s.owner_id=? "
                     "ORDER BY s.period_end DESC, s.id DESC", (contract_id, owner))
    else:
        rows = fetch(f"{_SELECT} WHERE s.owner_id=? ORDER BY s.period_end DESC, s.id DESC",
                     (owner,))
    return [_row(r) for r in rows]


@router.get("/pending", response_model=list[PendingAbrechnungOut])
def pending(owner: int = Depends(require_auth)):
    """Tenancies whose Abrechnung for a finished year is not recorded yet,
    with the §556 deadline. See nk_settlement_logic.pending_abrechnungen."""
    contracts = fetch("""
        SELECT c.id, c.tenant_id, c.apartment_id, c.start_date, c.end_date,
               c.nebenkosten_vorauszahlung, t.name, a.name, p.name
        FROM contracts c
        JOIN tenants    t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE c.owner_id = ?
    """, (owner,))
    settlements = fetch("SELECT contract_id, period_start, period_end FROM nk_settlements "
                        "WHERE owner_id=?", (owner,))
    names = {r[0]: (r[6], r[7], r[8]) for r in contracts}
    due = logic.pending_abrechnungen([r[:6] for r in contracts], settlements, date.today())
    return [PendingAbrechnungOut(**d, tenant_name=names[d["contract_id"]][0],
                                 apartment_name=names[d["contract_id"]][1],
                                 property_name=names[d["contract_id"]][2])
            for d in due]


@router.post("/", response_model=NKSettlementOut, status_code=201)
def create_settlement(body: NKSettlementIn, owner: int = Depends(require_auth)):
    _own_contract(body.contract_id, owner)
    new_id = execute_returning("""
        INSERT INTO nk_settlements
            (contract_id, period_start, period_end, amount, issued_date, note, owner_id)
        VALUES (?,?,?,?,?,?,?) RETURNING id
    """, (body.contract_id, body.period_start, body.period_end, body.amount,
          body.issued_date, body.note or None, owner))[0][0]
    return _one(new_id, owner)


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
    execute("""
        UPDATE nk_settlements
        SET contract_id=?, period_start=?, period_end=?, amount=?, issued_date=?, note=?
        WHERE id=? AND owner_id=?
    """, (body.contract_id, body.period_start, body.period_end, body.amount,
          body.issued_date, body.note or None, settlement_id, owner))
    return _one(settlement_id, owner)


@router.delete("/{settlement_id}", status_code=204)
def delete_settlement(settlement_id: int, owner: int = Depends(require_auth)):
    """Linked payments stay: the money moved whether or not the record does.
    They lose the link (ON DELETE SET NULL) and keep their kind."""
    _own_settlement(settlement_id, owner)
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
