from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import fetch, execute, get_conn, put_conn

router = APIRouter(prefix="/co-tenants", tags=["Co-Tenants"])


class CoTenantIn(BaseModel):
    contract_id: int
    name: str
    gender: str = "diverse"
    email: Optional[str] = None
    in_contract: bool = False


class CoTenantOut(BaseModel):
    id: int
    contract_id: int
    name: str
    gender: str
    email: Optional[str] = None
    in_contract: bool


def _row(r) -> CoTenantOut:
    return CoTenantOut(id=r[0], contract_id=r[1], name=r[2],
                       gender=r[3], email=r[4], in_contract=bool(r[5]))


@router.get("/", response_model=list[CoTenantOut])
def list_co_tenants(contract_id: int):
    rows = fetch("SELECT id,contract_id,name,gender,email,in_contract FROM co_tenants WHERE contract_id=? ORDER BY name",
                 (contract_id,))
    return [_row(r) for r in rows]


@router.post("/", response_model=CoTenantOut, status_code=201)
def create_co_tenant(body: CoTenantIn):
    if not fetch("SELECT id FROM contracts WHERE id=?", (body.contract_id,)):
        raise HTTPException(404, "Contract not found")
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO co_tenants (contract_id, name, gender, email, in_contract)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (body.contract_id, body.name, body.gender, body.email, int(body.in_contract)))
        new_id = c.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    rows = fetch("SELECT id,contract_id,name,gender,email,in_contract FROM co_tenants WHERE id=?", (new_id,))
    return _row(rows[0])


@router.put("/{ct_id}", response_model=CoTenantOut)
def update_co_tenant(ct_id: int, body: CoTenantIn):
    if not fetch("SELECT id FROM co_tenants WHERE id=?", (ct_id,)):
        raise HTTPException(404, "Co-tenant not found")
    execute("UPDATE co_tenants SET name=?,gender=?,email=?,in_contract=? WHERE id=?",
            (body.name, body.gender, body.email, int(body.in_contract), ct_id))
    rows = fetch("SELECT id,contract_id,name,gender,email,in_contract FROM co_tenants WHERE id=?", (ct_id,))
    return _row(rows[0])


@router.delete("/{ct_id}", status_code=204)
def delete_co_tenant(ct_id: int):
    if not fetch("SELECT id FROM co_tenants WHERE id=?", (ct_id,)):
        raise HTTPException(404, "Co-tenant not found")
    execute("DELETE FROM co_tenants WHERE id=?", (ct_id,))
