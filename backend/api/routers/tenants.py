from fastapi import APIRouter, Depends, HTTPException
from db import fetch, execute, execute_returning
from auth import require_auth
from api.schemas.tenant import TenantIn, TenantOut

router = APIRouter(prefix="/tenants", tags=["Tenants"])

_COLS = "id, name, email, phone, gender"


def _row(r) -> TenantOut:
    return TenantOut(id=r[0], name=r[1], email=r[2], phone=r[3], gender=r[4])


@router.get("/", response_model=list[TenantOut])
def list_tenants(owner: int = Depends(require_auth)):
    rows = fetch(f"SELECT {_COLS} FROM tenants WHERE owner_id=? ORDER BY name",
                 (owner,))
    return [_row(r) for r in rows]


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant_id: int, owner: int = Depends(require_auth)):
    rows = fetch(f"SELECT {_COLS} FROM tenants WHERE id=? AND owner_id=?",
                 (tenant_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _row(rows[0])


@router.post("/", response_model=TenantOut, status_code=201)
def create_tenant(body: TenantIn, owner: int = Depends(require_auth)):
    # Named columns rather than db.insert(): that helper is positional and
    # assumes owner_id is the last column, which stops holding as soon as a
    # column is added after it (phone was).
    new_id = execute_returning("""
        INSERT INTO tenants (name, email, phone, gender, owner_id)
        VALUES (?,?,?,?,?) RETURNING id
    """, (body.name, body.email, body.phone, body.gender, owner))[0][0]
    return TenantOut(id=new_id, name=body.name, email=body.email,
                     phone=body.phone, gender=body.gender)


@router.put("/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, body: TenantIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM tenants WHERE id=? AND owner_id=?", (tenant_id, owner)):
        raise HTTPException(status_code=404, detail="Tenant not found")
    execute("UPDATE tenants SET name=?, email=?, phone=?, gender=? WHERE id=? AND owner_id=?",
            (body.name, body.email, body.phone, body.gender, tenant_id, owner))
    return TenantOut(id=tenant_id, name=body.name, email=body.email,
                     phone=body.phone, gender=body.gender)


@router.delete("/{tenant_id}", status_code=204)
def delete_tenant(tenant_id: int, owner: int = Depends(require_auth)):
    import psycopg2.errors
    if not fetch("SELECT id FROM tenants WHERE id=? AND owner_id=?", (tenant_id, owner)):
        raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        execute("DELETE FROM tenants WHERE id=? AND owner_id=?", (tenant_id, owner))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(status_code=409,
                            detail="Tenant still has contracts — delete them first.")
