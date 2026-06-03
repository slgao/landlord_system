from fastapi import APIRouter, HTTPException
from db import fetch, execute, insert
from api.schemas.tenant import TenantIn, TenantOut

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get("/", response_model=list[TenantOut])
def list_tenants():
    rows = fetch("SELECT id, name, email, gender FROM tenants ORDER BY name")
    return [TenantOut(id=r[0], name=r[1], email=r[2], gender=r[3]) for r in rows]


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: int):
    rows = fetch("SELECT id, name, email, gender FROM tenants WHERE id=?", (tenant_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    r = rows[0]
    return TenantOut(id=r[0], name=r[1], email=r[2], gender=r[3])


@router.post("/", response_model=TenantOut, status_code=201)
def create_tenant(body: TenantIn):
    insert("tenants", (body.name, body.email, body.gender))
    rows = fetch("SELECT id FROM tenants WHERE name=? ORDER BY id DESC LIMIT 1",
                 (body.name,))
    return TenantOut(id=rows[0][0], name=body.name,
                     email=body.email, gender=body.gender)


@router.put("/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, body: TenantIn):
    rows = fetch("SELECT id FROM tenants WHERE id=?", (tenant_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    execute("UPDATE tenants SET name=?, email=?, gender=? WHERE id=?",
            (body.name, body.email, body.gender, tenant_id))
    return TenantOut(id=tenant_id, name=body.name,
                     email=body.email, gender=body.gender)


@router.delete("/{tenant_id}", status_code=204)
def delete_tenant(tenant_id: int):
    import psycopg2.errors
    rows = fetch("SELECT id FROM tenants WHERE id=?", (tenant_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(status_code=409,
                            detail="Tenant still has contracts — delete them first.")
