from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import fetch, execute, insert
from auth import require_auth

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
def list_co_tenants(contract_id: int, owner: int = Depends(require_auth)):
    rows = fetch("SELECT id,contract_id,name,gender,email,in_contract FROM co_tenants "
                 "WHERE contract_id=? AND owner_id=? ORDER BY name", (contract_id, owner))
    return [_row(r) for r in rows]


@router.post("/", response_model=CoTenantOut, status_code=201)
def create_co_tenant(body: CoTenantIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM contracts WHERE id=? AND owner_id=?", (body.contract_id, owner)):
        raise HTTPException(404, "Contract not found")
    new_id = insert("co_tenants", (body.contract_id, body.name, body.gender,
                                   body.email, int(body.in_contract)))
    rows = fetch("SELECT id,contract_id,name,gender,email,in_contract FROM co_tenants WHERE id=?",
                 (new_id,))
    return _row(rows[0])


@router.put("/{ct_id}", response_model=CoTenantOut)
def update_co_tenant(ct_id: int, body: CoTenantIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM co_tenants WHERE id=? AND owner_id=?", (ct_id, owner)):
        raise HTTPException(404, "Co-tenant not found")
    execute("UPDATE co_tenants SET name=?,gender=?,email=?,in_contract=? WHERE id=? AND owner_id=?",
            (body.name, body.gender, body.email, int(body.in_contract), ct_id, owner))
    rows = fetch("SELECT id,contract_id,name,gender,email,in_contract FROM co_tenants WHERE id=?",
                 (ct_id,))
    return _row(rows[0])


@router.delete("/{ct_id}", status_code=204)
def delete_co_tenant(ct_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM co_tenants WHERE id=? AND owner_id=?", (ct_id, owner)):
        raise HTTPException(404, "Co-tenant not found")
    execute("DELETE FROM co_tenants WHERE id=? AND owner_id=?", (ct_id, owner))
