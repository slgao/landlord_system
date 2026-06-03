from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import fetch, execute, insert

router = APIRouter(prefix="/flat-costs", tags=["Flat Costs"])


class FlatCostIn(BaseModel):
    apartment_id: int
    cost_type: str
    amount: float
    frequency: str = "monthly"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class FlatCostOut(BaseModel):
    id: int
    apartment_id: int
    apartment_name: Optional[str] = None
    property_name: Optional[str] = None
    cost_type: str
    amount: float
    frequency: str
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


def _row(r) -> FlatCostOut:
    return FlatCostOut(
        id=r[0], apartment_id=r[1],
        apartment_name=r[2], property_name=r[3],
        cost_type=r[4], amount=float(r[5]),
        frequency=r[6] or "monthly",
        valid_from=r[7] if r[7] and r[7] != "None" else None,
        valid_to=r[8] if r[8] and r[8] != "None" else None,
    )


_SELECT = """
    SELECT fc.id, fc.apartment_id, a.name, p.name,
           fc.cost_type, fc.amount, fc.frequency, fc.valid_from, fc.valid_to
    FROM flat_costs fc
    JOIN apartments a ON a.id = fc.apartment_id
    JOIN properties p ON p.id = a.property_id
"""


@router.get("/", response_model=list[FlatCostOut])
def list_flat_costs(apartment_id: int | None = None):
    if apartment_id:
        rows = fetch(f"{_SELECT} WHERE fc.apartment_id=? ORDER BY fc.cost_type", (apartment_id,))
    else:
        rows = fetch(f"{_SELECT} ORDER BY p.name, a.name, fc.cost_type")
    return [_row(r) for r in rows]


@router.get("/{cost_id}", response_model=FlatCostOut)
def get_flat_cost(cost_id: int):
    rows = fetch(f"{_SELECT} WHERE fc.id=?", (cost_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Flat cost not found")
    return _row(rows[0])


@router.post("/", response_model=FlatCostOut, status_code=201)
def create_flat_cost(body: FlatCostIn):
    insert("flat_costs", (body.apartment_id, body.cost_type, body.amount,
                          body.frequency, body.valid_from, body.valid_to))
    rows = fetch(f"{_SELECT} WHERE fc.apartment_id=? ORDER BY fc.id DESC LIMIT 1",
                 (body.apartment_id,))
    return _row(rows[0])


@router.put("/{cost_id}", response_model=FlatCostOut)
def update_flat_cost(cost_id: int, body: FlatCostIn):
    rows = fetch("SELECT id FROM flat_costs WHERE id=?", (cost_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Flat cost not found")
    execute("""
        UPDATE flat_costs SET apartment_id=?, cost_type=?, amount=?,
               frequency=?, valid_from=?, valid_to=?
        WHERE id=?
    """, (body.apartment_id, body.cost_type, body.amount,
          body.frequency, body.valid_from, body.valid_to, cost_id))
    rows = fetch(f"{_SELECT} WHERE fc.id=?", (cost_id,))
    return _row(rows[0])


@router.delete("/{cost_id}", status_code=204)
def delete_flat_cost(cost_id: int):
    rows = fetch("SELECT id FROM flat_costs WHERE id=?", (cost_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Flat cost not found")
    execute("DELETE FROM flat_costs WHERE id=?", (cost_id,))
