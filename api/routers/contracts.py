from fastapi import APIRouter, HTTPException
from db import fetch
from api.schemas.contract import ContractOut

router = APIRouter(prefix="/contracts", tags=["Contracts"])


def _row_to_contract(r) -> ContractOut:
    return ContractOut(
        id=r[0], tenant_id=r[1], tenant_name=r[2],
        apartment_id=r[3], apartment_name=r[4], property_name=r[5],
        rent=r[6],
        start_date=r[7],
        end_date=r[8] if r[8] and r[8] != "None" else None,
        terminated=bool(r[9]),
    )


@router.get("/", response_model=list[ContractOut])
def list_contracts(active_only: bool = False):
    where = "WHERE COALESCE(c.terminated, 0) = 0" if active_only else ""
    rows = fetch(f"""
        SELECT c.id, c.tenant_id, t.name, c.apartment_id, a.name, p.name,
               c.rent, c.start_date, c.end_date, c.terminated
        FROM contracts c
        JOIN tenants    t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        {where}
        ORDER BY c.start_date DESC
    """)
    return [_row_to_contract(r) for r in rows]


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(contract_id: int):
    rows = fetch("""
        SELECT c.id, c.tenant_id, t.name, c.apartment_id, a.name, p.name,
               c.rent, c.start_date, c.end_date, c.terminated
        FROM contracts c
        JOIN tenants    t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE c.id=?
    """, (contract_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    return _row_to_contract(rows[0])


@router.get("/tenant/{tenant_id}", response_model=list[ContractOut])
def contracts_for_tenant(tenant_id: int):
    rows = fetch("""
        SELECT c.id, c.tenant_id, t.name, c.apartment_id, a.name, p.name,
               c.rent, c.start_date, c.end_date, c.terminated
        FROM contracts c
        JOIN tenants    t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE c.tenant_id=?
        ORDER BY c.start_date DESC
    """, (tenant_id,))
    return [_row_to_contract(r) for r in rows]
