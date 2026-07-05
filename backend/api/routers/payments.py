from fastapi import APIRouter, HTTPException
from db import fetch, execute, get_conn, put_conn
from api.schemas.payment import PaymentIn, PaymentOut

router = APIRouter(prefix="/payments", tags=["Payments"])


def _row(r) -> PaymentOut:
    return PaymentOut(
        id=r[0], contract_id=r[1],
        tenant_name=r[2], apartment_name=r[3],
        amount=float(r[4]), payment_date=r[5],
        currency=r[6] or "EUR",
        orig_amount=float(r[7]) if r[7] is not None else None,
        orig_currency=r[8],
    )


_SELECT = """
    SELECT p.id, p.contract_id, t.name, a.name, p.amount, p.payment_date,
           COALESCE(p.currency,'EUR'), p.orig_amount, p.orig_currency
    FROM payments p
    JOIN contracts c ON c.id = p.contract_id
    JOIN tenants t ON t.id = c.tenant_id
    JOIN apartments a ON a.id = c.apartment_id
"""


@router.get("/", response_model=list[PaymentOut])
def list_payments(contract_id: int | None = None, tenant_id: int | None = None):
    if contract_id:
        rows = fetch(f"{_SELECT} WHERE p.contract_id=? ORDER BY p.payment_date DESC", (contract_id,))
    elif tenant_id:
        rows = fetch(f"{_SELECT} WHERE c.tenant_id=? ORDER BY p.payment_date DESC", (tenant_id,))
    else:
        rows = fetch(f"{_SELECT} ORDER BY p.payment_date DESC")
    return [_row(r) for r in rows]


@router.post("/", response_model=PaymentOut, status_code=201)
def create_payment(body: PaymentIn):
    if not fetch("SELECT id FROM contracts WHERE id=?", (body.contract_id,)):
        raise HTTPException(status_code=404, detail="Contract not found")
    conn = get_conn()
    try:
        c = conn.cursor()
        # EUR is the accounting currency; `amount` is always the EUR value.
        # A foreign tender is stored only as a note (orig_amount/orig_currency).
        has_foreign = bool(body.orig_currency) and body.orig_currency != "EUR"
        orig_currency = body.orig_currency if has_foreign else None
        orig_amount = body.orig_amount if has_foreign else None
        c.execute("""
            INSERT INTO payments (contract_id, amount, payment_date, currency, orig_amount, orig_currency)
            VALUES (%s,%s,%s,'EUR',%s,%s) RETURNING id
        """, (body.contract_id, body.amount, body.payment_date, orig_amount, orig_currency))
        new_id = c.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    rows = fetch(f"{_SELECT} WHERE p.id=?", (new_id,))
    return _row(rows[0])


@router.delete("/{payment_id}", status_code=204)
def delete_payment(payment_id: int):
    if not fetch("SELECT id FROM payments WHERE id=?", (payment_id,)):
        raise HTTPException(status_code=404, detail="Payment not found")
    execute("DELETE FROM payments WHERE id=?", (payment_id,))
