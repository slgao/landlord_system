from fastapi import APIRouter, HTTPException
from db import fetch, execute, insert
from api.schemas.payment import PaymentIn, PaymentOut

router = APIRouter(prefix="/payments", tags=["Payments"])


def _row_to_payment(r) -> PaymentOut:
    return PaymentOut(
        id=r[0], contract_id=r[1],
        tenant_name=r[2], apartment_name=r[3],
        amount=r[4], payment_date=r[5],
    )


@router.get("/", response_model=list[PaymentOut])
def list_payments(contract_id: int | None = None, tenant_id: int | None = None):
    if contract_id:
        rows = fetch("""
            SELECT p.id, p.contract_id, t.name, a.name, p.amount, p.payment_date
            FROM payments p
            JOIN contracts c ON c.id = p.contract_id
            JOIN tenants t ON t.id = c.tenant_id
            JOIN apartments a ON a.id = c.apartment_id
            WHERE p.contract_id=?
            ORDER BY p.payment_date DESC
        """, (contract_id,))
    elif tenant_id:
        rows = fetch("""
            SELECT p.id, p.contract_id, t.name, a.name, p.amount, p.payment_date
            FROM payments p
            JOIN contracts c ON c.id = p.contract_id
            JOIN tenants t ON t.id = c.tenant_id
            JOIN apartments a ON a.id = c.apartment_id
            WHERE c.tenant_id=?
            ORDER BY p.payment_date DESC
        """, (tenant_id,))
    else:
        rows = fetch("""
            SELECT p.id, p.contract_id, t.name, a.name, p.amount, p.payment_date
            FROM payments p
            JOIN contracts c ON c.id = p.contract_id
            JOIN tenants t ON t.id = c.tenant_id
            JOIN apartments a ON a.id = c.apartment_id
            ORDER BY p.payment_date DESC
        """)
    return [_row_to_payment(r) for r in rows]


@router.post("/", response_model=PaymentOut, status_code=201)
def create_payment(body: PaymentIn):
    contract = fetch("SELECT id FROM contracts WHERE id=?", (body.contract_id,))
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    insert("payments", (body.contract_id, body.amount, body.payment_date))
    rows = fetch("""
        SELECT p.id, p.contract_id, t.name, a.name, p.amount, p.payment_date
        FROM payments p
        JOIN contracts c ON c.id = p.contract_id
        JOIN tenants t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        WHERE p.contract_id=? ORDER BY p.id DESC LIMIT 1
    """, (body.contract_id,))
    return _row_to_payment(rows[0])


@router.delete("/{payment_id}", status_code=204)
def delete_payment(payment_id: int):
    rows = fetch("SELECT id FROM payments WHERE id=?", (payment_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Payment not found")
    execute("DELETE FROM payments WHERE id=?", (payment_id,))
