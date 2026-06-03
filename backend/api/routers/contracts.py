from fastapi import APIRouter, HTTPException
from db import fetch, execute, insert
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


@router.get("/", response_model=list[ContractOut])
def list_contracts(active_only: bool = False):
    where = "WHERE COALESCE(c.terminated, 0) = 0" if active_only else ""
    rows = fetch(f"{_SELECT} {where} ORDER BY c.start_date DESC")
    return [_row(r) for r in rows]


# Specific paths must come before /{contract_id} to avoid being captured by it
@router.get("/tenant/{tenant_id}", response_model=list[ContractOut])
def contracts_for_tenant(tenant_id: int):
    rows = fetch(f"{_SELECT} WHERE c.tenant_id=? ORDER BY c.start_date DESC", (tenant_id,))
    return [_row(r) for r in rows]


@router.get("/kaution-overview", response_model=list)
def kaution_overview_top():
    return kaution_overview()


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(contract_id: int):
    rows = fetch(f"{_SELECT} WHERE c.id=?", (contract_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _row(rows[0])


@router.post("/", response_model=ContractOut, status_code=201)
def create_contract(body: ContractIn):
    from db import get_conn, put_conn
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO contracts
              (tenant_id, apartment_id, rent, currency, start_date, end_date,
               kaution_amount, kaution_currency, kaution_paid_date,
               kaution_returned_date, kaution_returned_amount, terminated)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (body.tenant_id, body.apartment_id, body.rent, body.currency,
              body.start_date, body.end_date or None,
              body.kaution_amount, body.kaution_currency,
              body.kaution_paid_date or None,
              body.kaution_returned_date or None,
              body.kaution_returned_amount,
              int(body.terminated)))
        new_id = c.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    rows = fetch(f"{_SELECT} WHERE c.id=?", (new_id,))
    return _row(rows[0])


@router.put("/{contract_id}", response_model=ContractOut)
def update_contract(contract_id: int, body: ContractIn):
    rows = fetch("SELECT id FROM contracts WHERE id=?", (contract_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    execute("""
        UPDATE contracts SET
          tenant_id=?, apartment_id=?, rent=?, currency=?,
          start_date=?, end_date=?,
          kaution_amount=?, kaution_currency=?, kaution_paid_date=?,
          kaution_returned_date=?, kaution_returned_amount=?, terminated=?
        WHERE id=?
    """, (body.tenant_id, body.apartment_id, body.rent, body.currency,
          body.start_date, body.end_date or None,
          body.kaution_amount, body.kaution_currency,
          body.kaution_paid_date or None,
          body.kaution_returned_date or None,
          body.kaution_returned_amount,
          int(body.terminated), contract_id))
    rows = fetch(f"{_SELECT} WHERE c.id=?", (contract_id,))
    return _row(rows[0])


@router.post("/{contract_id}/terminate", response_model=ContractOut)
def terminate_contract(contract_id: int, end_date: str | None = None):
    rows = fetch("SELECT id FROM contracts WHERE id=?", (contract_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    from datetime import date as _date
    ed = end_date or str(_date.today())
    execute("UPDATE contracts SET terminated=1, end_date=? WHERE id=?", (ed, contract_id))
    rows = fetch(f"{_SELECT} WHERE c.id=?", (contract_id,))
    return _row(rows[0])


@router.post("/{contract_id}/reopen", response_model=ContractOut)
def reopen_contract(contract_id: int):
    rows = fetch("SELECT id FROM contracts WHERE id=?", (contract_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    execute("UPDATE contracts SET terminated=0, end_date=NULL WHERE id=?", (contract_id,))
    rows = fetch(f"{_SELECT} WHERE c.id=?", (contract_id,))
    return _row(rows[0])


from pydantic import BaseModel as _BM
from typing import Optional as _Opt

class KautionReturnIn(_BM):
    returned_date: str
    returned_amount: float


@router.post("/{contract_id}/kaution-return", response_model=ContractOut)
def mark_kaution_returned(contract_id: int, body: KautionReturnIn):
    rows = fetch("SELECT id FROM contracts WHERE id=?", (contract_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    execute("UPDATE contracts SET kaution_returned_date=?, kaution_returned_amount=? WHERE id=?",
            (body.returned_date, body.returned_amount, contract_id))
    rows = fetch(f"{_SELECT} WHERE c.id=?", (contract_id,))
    return _row(rows[0])


@router.post("/{contract_id}/kaution-return/clear", response_model=ContractOut)
def clear_kaution_return(contract_id: int):
    rows = fetch("SELECT id FROM contracts WHERE id=?", (contract_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    execute("UPDATE contracts SET kaution_returned_date=NULL, kaution_returned_amount=NULL WHERE id=?",
            (contract_id,))
    rows = fetch(f"{_SELECT} WHERE c.id=?", (contract_id,))
    return _row(rows[0])


@router.get("/kaution-overview", response_model=list)
def kaution_overview():
    rows = fetch("""
        SELECT c.id, t.name, a.name, p.name,
               c.kaution_amount, COALESCE(c.kaution_currency,'EUR'),
               c.kaution_paid_date, c.kaution_returned_date, c.kaution_returned_amount,
               COALESCE((SELECT SUM(amount) FROM kaution_deductions WHERE contract_id=c.id), 0)
        FROM contracts c
        JOIN tenants t ON t.id=c.tenant_id
        JOIN apartments a ON a.id=c.apartment_id
        JOIN properties p ON p.id=a.property_id
        WHERE c.kaution_amount IS NOT NULL AND c.kaution_amount > 0
        ORDER BY t.name
    """)
    result = []
    for r in rows:
        k_amt = float(r[4]) if r[4] else 0.0
        deducted = float(r[9]) if r[9] else 0.0
        result.append({
            "contract_id": r[0], "tenant_name": r[1], "apartment_name": r[2],
            "property_name": r[3], "kaution_amount": k_amt,
            "kaution_currency": r[5], "kaution_paid_date": r[6],
            "kaution_returned_date": r[7],
            "kaution_returned_amount": float(r[8]) if r[8] else None,
            "deducted": deducted, "balance": round(k_amt - deducted, 2),
        })
    return result


@router.delete("/{contract_id}", status_code=204)
def delete_contract(contract_id: int):
    rows = fetch("SELECT id FROM contracts WHERE id=?", (contract_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    execute("DELETE FROM payments WHERE contract_id=?", (contract_id,))
    execute("DELETE FROM contracts WHERE id=?", (contract_id,))
