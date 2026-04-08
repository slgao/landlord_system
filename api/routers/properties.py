from fastapi import APIRouter, HTTPException
from db import fetch, execute, insert
from api.schemas.property import PropertyIn, PropertyOut

router = APIRouter(prefix="/properties", tags=["Properties"])


@router.get("/", response_model=list[PropertyOut])
def list_properties():
    rows = fetch("SELECT id, name, address FROM properties ORDER BY name")
    return [PropertyOut(id=r[0], name=r[1], address=r[2]) for r in rows]


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: int):
    rows = fetch("SELECT id, name, address FROM properties WHERE id=?", (property_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Property not found")
    r = rows[0]
    return PropertyOut(id=r[0], name=r[1], address=r[2])


@router.post("/", response_model=PropertyOut, status_code=201)
def create_property(body: PropertyIn):
    insert("properties", (body.name, body.address))
    rows = fetch("SELECT id, name, address FROM properties WHERE name=? ORDER BY id DESC LIMIT 1",
                 (body.name,))
    r = rows[0]
    return PropertyOut(id=r[0], name=r[1], address=r[2])


@router.put("/{property_id}", response_model=PropertyOut)
def update_property(property_id: int, body: PropertyIn):
    rows = fetch("SELECT id FROM properties WHERE id=?", (property_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Property not found")
    execute("UPDATE properties SET name=?, address=? WHERE id=?",
            (body.name, body.address, property_id))
    return PropertyOut(id=property_id, name=body.name, address=body.address)


@router.delete("/{property_id}", status_code=204)
def delete_property(property_id: int):
    rows = fetch("SELECT id FROM properties WHERE id=?", (property_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Property not found")
    execute("DELETE FROM properties WHERE id=?", (property_id,))
