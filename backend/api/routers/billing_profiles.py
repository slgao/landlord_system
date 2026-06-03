import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional
from db import fetch, execute, get_conn, put_conn
from datetime import date

router = APIRouter(prefix="/billing-profiles", tags=["Billing Profiles"])


class BillingProfileIn(BaseModel):
    tenant_id: int
    label: str
    data: Any


class BillingProfileOut(BaseModel):
    id: int
    tenant_id: int
    label: str
    created_date: Optional[str]
    data: Any


def _row(r) -> BillingProfileOut:
    return BillingProfileOut(id=r[0], tenant_id=r[1], label=r[2],
                             created_date=r[3], data=json.loads(r[4]) if r[4] else {})


@router.get("/", response_model=list[BillingProfileOut])
def list_profiles(tenant_id: int):
    rows = fetch("SELECT id,tenant_id,label,created_date,data FROM billing_profiles WHERE tenant_id=? ORDER BY label",
                 (tenant_id,))
    return [_row(r) for r in rows]


@router.post("/", response_model=BillingProfileOut, status_code=201)
def create_profile(body: BillingProfileIn):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO billing_profiles (tenant_id, label, created_date, data)
            VALUES (%s,%s,%s,%s) RETURNING id
        """, (body.tenant_id, body.label, str(date.today()), json.dumps(body.data)))
        new_id = c.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    rows = fetch("SELECT id,tenant_id,label,created_date,data FROM billing_profiles WHERE id=?", (new_id,))
    return _row(rows[0])


@router.put("/{profile_id}", response_model=BillingProfileOut)
def update_profile(profile_id: int, body: BillingProfileIn):
    if not fetch("SELECT id FROM billing_profiles WHERE id=?", (profile_id,)):
        raise HTTPException(404, "Profile not found")
    execute("UPDATE billing_profiles SET label=?,data=? WHERE id=?",
            (body.label, json.dumps(body.data), profile_id))
    rows = fetch("SELECT id,tenant_id,label,created_date,data FROM billing_profiles WHERE id=?", (profile_id,))
    return _row(rows[0])


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int):
    if not fetch("SELECT id FROM billing_profiles WHERE id=?", (profile_id,)):
        raise HTTPException(404, "Profile not found")
    execute("DELETE FROM billing_profiles WHERE id=?", (profile_id,))
