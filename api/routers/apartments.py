from fastapi import APIRouter, HTTPException
from db import fetch
from api.schemas.apartment import ApartmentOut

router = APIRouter(prefix="/apartments", tags=["Apartments"])


@router.get("/", response_model=list[ApartmentOut])
def list_apartments(property_id: int | None = None):
    if property_id:
        rows = fetch("""
            SELECT a.id, a.property_id, p.name, a.name, a.flat
            FROM apartments a JOIN properties p ON a.property_id = p.id
            WHERE a.property_id=? ORDER BY a.flat, a.name
        """, (property_id,))
    else:
        rows = fetch("""
            SELECT a.id, a.property_id, p.name, a.name, a.flat
            FROM apartments a JOIN properties p ON a.property_id = p.id
            ORDER BY p.name, a.flat, a.name
        """)
    return [
        ApartmentOut(id=r[0], property_id=r[1], property_name=r[2],
                     name=r[3], flat=r[4])
        for r in rows
    ]


@router.get("/{apartment_id}", response_model=ApartmentOut)
def get_apartment(apartment_id: int):
    rows = fetch("""
        SELECT a.id, a.property_id, p.name, a.name, a.flat
        FROM apartments a JOIN properties p ON a.property_id = p.id
        WHERE a.id=?
    """, (apartment_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Apartment not found")
    r = rows[0]
    return ApartmentOut(id=r[0], property_id=r[1], property_name=r[2],
                        name=r[3], flat=r[4])
