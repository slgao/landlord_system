from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import fetch, execute, get_conn, put_conn

router = APIRouter(prefix="/kaution-deductions", tags=["Kaution"])


class KautionDeductionIn(BaseModel):
    contract_id: int
    date: str
    amount: float
    category: str
    reason: Optional[str] = None


class KautionDeductionOut(BaseModel):
    id: int
    contract_id: int
    date: str
    amount: float
    category: str
    reason: Optional[str] = None


def _row(r) -> KautionDeductionOut:
    return KautionDeductionOut(id=r[0], contract_id=r[1], date=r[2],
                               amount=float(r[3]), category=r[4], reason=r[5])


@router.get("/", response_model=list[KautionDeductionOut])
def list_deductions(contract_id: int):
    rows = fetch("""
        SELECT id,contract_id,date,amount,category,reason
        FROM kaution_deductions WHERE contract_id=? ORDER BY date
    """, (contract_id,))
    return [_row(r) for r in rows]


@router.post("/", response_model=KautionDeductionOut, status_code=201)
def create_deduction(body: KautionDeductionIn):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO kaution_deductions (contract_id,date,amount,category,reason)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (body.contract_id, body.date, body.amount, body.category, body.reason))
        new_id = c.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    rows = fetch("SELECT id,contract_id,date,amount,category,reason FROM kaution_deductions WHERE id=?", (new_id,))
    return _row(rows[0])


@router.delete("/{ded_id}", status_code=204)
def delete_deduction(ded_id: int):
    if not fetch("SELECT id FROM kaution_deductions WHERE id=?", (ded_id,)):
        raise HTTPException(404, "Deduction not found")
    execute("DELETE FROM kaution_deductions WHERE id=?", (ded_id,))
