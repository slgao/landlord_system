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


@router.put("/{ded_id}", response_model=KautionDeductionOut)
def update_deduction(ded_id: int, body: KautionDeductionIn):
    if not fetch("SELECT id FROM kaution_deductions WHERE id=?", (ded_id,)):
        raise HTTPException(404, "Deduction not found")
    execute("""
        UPDATE kaution_deductions
        SET date=?, amount=?, category=?, reason=?
        WHERE id=?
    """, (body.date, body.amount, body.category, body.reason, ded_id))
    rows = fetch("SELECT id,contract_id,date,amount,category,reason FROM kaution_deductions WHERE id=?", (ded_id,))
    return _row(rows[0])


@router.delete("/{ded_id}", status_code=204)
def delete_deduction(ded_id: int):
    if not fetch("SELECT id FROM kaution_deductions WHERE id=?", (ded_id,)):
        raise HTTPException(404, "Deduction not found")
    execute("DELETE FROM kaution_deductions WHERE id=?", (ded_id,))


# ---------------------------------------------------------------------------
# Kaution payments (installments the tenant actually paid)
# ---------------------------------------------------------------------------

payments_router = APIRouter(prefix="/kaution-payments", tags=["Kaution"])


class KautionPaymentIn(BaseModel):
    contract_id: int
    date: str
    amount: float
    note: Optional[str] = None


class KautionPaymentOut(BaseModel):
    id: int
    contract_id: int
    date: str
    amount: float
    note: Optional[str] = None


def _payment_row(r) -> KautionPaymentOut:
    return KautionPaymentOut(id=r[0], contract_id=r[1], date=r[2],
                             amount=float(r[3]), note=r[4])


@payments_router.get("/", response_model=list[KautionPaymentOut])
def list_payments(contract_id: int):
    rows = fetch("""
        SELECT id,contract_id,date,amount,note
        FROM kaution_payments WHERE contract_id=? ORDER BY date
    """, (contract_id,))
    return [_payment_row(r) for r in rows]


@payments_router.post("/", response_model=KautionPaymentOut, status_code=201)
def create_payment(body: KautionPaymentIn):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO kaution_payments (contract_id,date,amount,note)
            VALUES (%s,%s,%s,%s) RETURNING id
        """, (body.contract_id, body.date, body.amount, body.note))
        new_id = c.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    rows = fetch("SELECT id,contract_id,date,amount,note FROM kaution_payments WHERE id=?", (new_id,))
    return _payment_row(rows[0])


@payments_router.put("/{pay_id}", response_model=KautionPaymentOut)
def update_payment(pay_id: int, body: KautionPaymentIn):
    if not fetch("SELECT id FROM kaution_payments WHERE id=?", (pay_id,)):
        raise HTTPException(404, "Payment not found")
    execute("""
        UPDATE kaution_payments
        SET date=?, amount=?, note=?
        WHERE id=?
    """, (body.date, body.amount, body.note, pay_id))
    rows = fetch("SELECT id,contract_id,date,amount,note FROM kaution_payments WHERE id=?", (pay_id,))
    return _payment_row(rows[0])


@payments_router.delete("/{pay_id}", status_code=204)
def delete_payment(pay_id: int):
    if not fetch("SELECT id FROM kaution_payments WHERE id=?", (pay_id,)):
        raise HTTPException(404, "Payment not found")
    execute("DELETE FROM kaution_payments WHERE id=?", (pay_id,))
