from fastapi import APIRouter, Depends, HTTPException
from db import fetch, execute, execute_returning
from auth import require_auth
from api.schemas.contract import ContractIn, ContractOut

router = APIRouter(prefix="/contracts", tags=["Contracts"])


def _row(r) -> ContractOut:
    return ContractOut(
        id=r[0], tenant_id=r[1], tenant_name=r[2],
        apartment_id=r[3], apartment_name=r[4], property_name=r[5],
        rent=float(r[6]),
        currency=r[7] or "EUR",
        start_date=r[8],
        end_date=r[9] if r[9] and r[9] != "None" else None,
        kaution_amount=float(r[10]) if r[10] else None,
        kaution_currency=r[11] or "EUR",
        kaution_paid_date=r[12] if r[12] and r[12] != "None" else None,
        kaution_returned_date=r[13] if r[13] and r[13] != "None" else None,
        kaution_returned_amount=float(r[14]) if r[14] else None,
        terminated=bool(r[15]),
    )


_SELECT = """
    SELECT c.id, c.tenant_id, t.name, c.apartment_id, a.name, p.name,
           c.rent, COALESCE(c.currency,'EUR'),
           c.start_date, c.end_date,
           c.kaution_amount, COALESCE(c.kaution_currency,'EUR'),
           c.kaution_paid_date, c.kaution_returned_date, c.kaution_returned_amount,
           c.terminated
    FROM contracts c
    JOIN tenants    t ON t.id = c.tenant_id
    JOIN apartments a ON a.id = c.apartment_id
    JOIN properties p ON p.id = a.property_id
"""


def _get(contract_id: int, owner: int):
    rows = fetch(f"{_SELECT} WHERE c.id=? AND c.owner_id=?", (contract_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    return rows[0]


def _assert_own(contract_id: int, owner: int):
    if not fetch("SELECT id FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner)):
        raise HTTPException(status_code=404, detail="Contract not found")


@router.get("/", response_model=list[ContractOut])
def list_contracts(active_only: bool = False, owner: int = Depends(require_auth)):
    where = "AND COALESCE(c.terminated, 0) = 0" if active_only else ""
    rows = fetch(f"{_SELECT} WHERE c.owner_id=? {where} ORDER BY c.start_date DESC", (owner,))
    return [_row(r) for r in rows]


# Specific paths must come before /{contract_id} to avoid being captured by it
@router.get("/tenant/{tenant_id}", response_model=list[ContractOut])
def contracts_for_tenant(tenant_id: int, owner: int = Depends(require_auth)):
    rows = fetch(f"{_SELECT} WHERE c.tenant_id=? AND c.owner_id=? ORDER BY c.start_date DESC",
                 (tenant_id, owner))
    return [_row(r) for r in rows]


@router.get("/kaution-overview", response_model=list)
def kaution_overview_top(owner: int = Depends(require_auth)):
    return kaution_overview(owner)


@router.get("/{contract_id}/occupancy")
def contract_occupancy(contract_id: int, owner: int = Depends(require_auth)):
    """Auto-detect how many persons the flat's utility costs are divided by.
    See the WG vs. single-household rule below."""
    row = fetch("SELECT apartment_id FROM contracts WHERE id=? AND owner_id=?",
                (contract_id, owner))
    if not row:
        raise HTTPException(status_code=404, detail="Contract not found")
    apartment_id = row[0][0]

    co = fetch("SELECT COUNT(*) FROM co_tenants WHERE contract_id=? AND owner_id=?",
               (contract_id, owner))
    co_count = int(co[0][0]) if co and co[0][0] else 0

    if co_count > 0:
        # Single household on one contract → main tenant covers the whole flat.
        auto_count = 1
    else:
        pf = fetch("""
            SELECT COUNT(DISTINCT c.tenant_id)
            FROM contracts c
            JOIN apartments a ON c.apartment_id = a.id
            WHERE c.owner_id = ?
              AND COALESCE(c.terminated, 0) = 0
              AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= date('now')::text)
              AND a.flat IS NOT NULL AND a.flat != ''
              AND a.property_id = (SELECT property_id FROM apartments WHERE id=?)
              AND a.flat = (SELECT flat FROM apartments WHERE id=?)
        """, (owner, apartment_id, apartment_id))
        auto_count = int(pf[0][0]) if pf and pf[0][0] else 1

    return {"auto_count": max(1, auto_count), "co_tenant_count": co_count}


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(contract_id: int, owner: int = Depends(require_auth)):
    return _row(_get(contract_id, owner))


@router.post("/", response_model=ContractOut, status_code=201)
def create_contract(body: ContractIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM tenants WHERE id=? AND owner_id=?", (body.tenant_id, owner)):
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not fetch("SELECT id FROM apartments WHERE id=? AND owner_id=?", (body.apartment_id, owner)):
        raise HTTPException(status_code=404, detail="Apartment not found")
    new_id = execute_returning("""
        INSERT INTO contracts
          (tenant_id, apartment_id, rent, currency, start_date, end_date,
           kaution_amount, kaution_currency, kaution_paid_date,
           kaution_returned_date, kaution_returned_amount, terminated, owner_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        RETURNING id
    """, (body.tenant_id, body.apartment_id, body.rent, body.currency,
          body.start_date, body.end_date or None,
          body.kaution_amount, body.kaution_currency,
          body.kaution_paid_date or None,
          body.kaution_returned_date or None,
          body.kaution_returned_amount,
          int(body.terminated), owner))[0][0]
    return _row(_get(new_id, owner))


@router.put("/{contract_id}", response_model=ContractOut)
def update_contract(contract_id: int, body: ContractIn, owner: int = Depends(require_auth)):
    _assert_own(contract_id, owner)
    if not fetch("SELECT id FROM tenants WHERE id=? AND owner_id=?", (body.tenant_id, owner)):
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not fetch("SELECT id FROM apartments WHERE id=? AND owner_id=?", (body.apartment_id, owner)):
        raise HTTPException(status_code=404, detail="Apartment not found")
    execute("""
        UPDATE contracts SET
          tenant_id=?, apartment_id=?, rent=?, currency=?,
          start_date=?, end_date=?,
          kaution_amount=?, kaution_currency=?, kaution_paid_date=?,
          kaution_returned_date=?, kaution_returned_amount=?, terminated=?
        WHERE id=? AND owner_id=?
    """, (body.tenant_id, body.apartment_id, body.rent, body.currency,
          body.start_date, body.end_date or None,
          body.kaution_amount, body.kaution_currency,
          body.kaution_paid_date or None,
          body.kaution_returned_date or None,
          body.kaution_returned_amount,
          int(body.terminated), contract_id, owner))
    return _row(_get(contract_id, owner))


@router.post("/{contract_id}/terminate", response_model=ContractOut)
def terminate_contract(contract_id: int, end_date: str | None = None,
                       owner: int = Depends(require_auth)):
    rows = fetch("SELECT end_date FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    from datetime import date as _date
    existing = rows[0][0]
    existing = existing if (existing and str(existing) != "None") else None
    if end_date:
        ed = end_date
    elif existing:
        ed = existing
    else:
        ed = str(_date.today())
    execute("UPDATE contracts SET terminated=1, end_date=? WHERE id=? AND owner_id=?",
            (ed, contract_id, owner))
    return _row(_get(contract_id, owner))


@router.post("/{contract_id}/reopen", response_model=ContractOut)
def reopen_contract(contract_id: int, owner: int = Depends(require_auth)):
    rows = fetch("SELECT end_date FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    from datetime import date as _date
    existing = rows[0][0]
    existing = existing if (existing and str(existing) != "None") else None
    keep_end = False
    if existing:
        try:
            keep_end = _date.fromisoformat(existing) > _date.today()
        except ValueError:
            keep_end = False
    if keep_end:
        execute("UPDATE contracts SET terminated=0 WHERE id=? AND owner_id=?", (contract_id, owner))
    else:
        execute("UPDATE contracts SET terminated=0, end_date=NULL WHERE id=? AND owner_id=?",
                (contract_id, owner))
    return _row(_get(contract_id, owner))


from pydantic import BaseModel as _BM
from typing import Optional as _Opt

class KautionReturnIn(_BM):
    returned_date: str
    returned_amount: float


class RentSettleIn(_BM):
    settled_until: _Opt[str] = None   # ISO date, or null/empty to clear


@router.post("/{contract_id}/settle-rent")
def settle_rent(contract_id: int, body: RentSettleIn, owner: int = Depends(require_auth)):
    _assert_own(contract_id, owner)
    settled = (body.settled_until or "").strip() or None
    execute("UPDATE contracts SET rent_settled_until=? WHERE id=? AND owner_id=?",
            (settled, contract_id, owner))
    return {"contract_id": contract_id, "rent_settled_until": settled}


@router.post("/{contract_id}/kaution-return", response_model=ContractOut)
def mark_kaution_returned(contract_id: int, body: KautionReturnIn,
                          owner: int = Depends(require_auth)):
    _assert_own(contract_id, owner)
    execute("UPDATE contracts SET kaution_returned_date=?, kaution_returned_amount=? "
            "WHERE id=? AND owner_id=?",
            (body.returned_date, body.returned_amount, contract_id, owner))
    return _row(_get(contract_id, owner))


@router.post("/{contract_id}/kaution-return/clear", response_model=ContractOut)
def clear_kaution_return(contract_id: int, owner: int = Depends(require_auth)):
    _assert_own(contract_id, owner)
    execute("UPDATE contracts SET kaution_returned_date=NULL, kaution_returned_amount=NULL "
            "WHERE id=? AND owner_id=?", (contract_id, owner))
    return _row(_get(contract_id, owner))


@router.get("/kaution-overview", response_model=list)
def kaution_overview(owner: int = Depends(require_auth)):
    rows = fetch("""
        SELECT c.id, t.name, a.name, p.name,
               c.kaution_amount, COALESCE(c.kaution_currency,'EUR'),
               c.kaution_paid_date, c.kaution_returned_date, c.kaution_returned_amount,
               COALESCE((SELECT SUM(amount) FROM kaution_deductions WHERE contract_id=c.id), 0),
               COALESCE((SELECT SUM(amount) FROM kaution_payments WHERE contract_id=c.id), 0)
        FROM contracts c
        JOIN tenants t ON t.id=c.tenant_id
        JOIN apartments a ON a.id=c.apartment_id
        JOIN properties p ON p.id=a.property_id
        WHERE c.owner_id = ?
          AND c.kaution_amount IS NOT NULL AND c.kaution_amount > 0
        ORDER BY t.name
    """, (owner,))
    result = []
    for r in rows:
        k_amt = float(r[4]) if r[4] else 0.0
        deducted = float(r[9]) if r[9] else 0.0
        installments = float(r[10]) if r[10] else 0.0
        paid_date = r[6] and str(r[6]) != "None"
        legacy_fully_paid = installments == 0.0 and bool(paid_date)
        paid = k_amt if legacy_fully_paid else installments
        result.append({
            "contract_id": r[0], "tenant_name": r[1], "apartment_name": r[2],
            "property_name": r[3], "kaution_amount": k_amt,
            "kaution_currency": r[5], "kaution_paid_date": r[6],
            "kaution_returned_date": r[7],
            "kaution_returned_amount": float(r[8]) if r[8] else None,
            "deducted": deducted, "paid": paid,
            "outstanding": round(k_amt - paid, 2),
            "balance": round(k_amt - deducted, 2),
        })
    return result


@router.delete("/{contract_id}", status_code=204)
def delete_contract(contract_id: int, owner: int = Depends(require_auth)):
    _assert_own(contract_id, owner)
    # Child rows (payments, kaution_*, co_tenants, reminders) cascade via FKs.
    execute("DELETE FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner))
