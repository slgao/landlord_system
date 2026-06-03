from fastapi import APIRouter, HTTPException
from db import fetch, execute, insert
from api.schemas.apartment import ApartmentIn, ApartmentOut

router = APIRouter(prefix="/apartments", tags=["Apartments"])


def _row(r) -> ApartmentOut:
    return ApartmentOut(id=r[0], property_id=r[1], property_name=r[2], name=r[3], flat=r[4])


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
    return [_row(r) for r in rows]


@router.get("/{apartment_id}", response_model=ApartmentOut)
def get_apartment(apartment_id: int):
    rows = fetch("""
        SELECT a.id, a.property_id, p.name, a.name, a.flat
        FROM apartments a JOIN properties p ON a.property_id = p.id
        WHERE a.id=?
    """, (apartment_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return _row(rows[0])


@router.post("/", response_model=ApartmentOut, status_code=201)
def create_apartment(body: ApartmentIn):
    props = fetch("SELECT id FROM properties WHERE id=?", (body.property_id,))
    if not props:
        raise HTTPException(status_code=404, detail="Property not found")
    insert("apartments", (body.property_id, body.name, body.flat))
    rows = fetch("""
        SELECT a.id, a.property_id, p.name, a.name, a.flat
        FROM apartments a JOIN properties p ON a.property_id = p.id
        WHERE a.property_id=? ORDER BY a.id DESC LIMIT 1
    """, (body.property_id,))
    return _row(rows[0])


@router.put("/{apartment_id}", response_model=ApartmentOut)
def update_apartment(apartment_id: int, body: ApartmentIn):
    rows = fetch("SELECT id FROM apartments WHERE id=?", (apartment_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Apartment not found")
    execute("UPDATE apartments SET property_id=?, name=?, flat=? WHERE id=?",
            (body.property_id, body.name, body.flat, apartment_id))
    rows = fetch("""
        SELECT a.id, a.property_id, p.name, a.name, a.flat
        FROM apartments a JOIN properties p ON a.property_id = p.id
        WHERE a.id=?
    """, (apartment_id,))
    return _row(rows[0])


@router.delete("/{apartment_id}", status_code=204)
def delete_apartment(apartment_id: int):
    import psycopg2.errors
    rows = fetch("SELECT id FROM apartments WHERE id=?", (apartment_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Apartment not found")
    try:
        execute("DELETE FROM apartments WHERE id=?", (apartment_id,))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(status_code=409,
                            detail="Apartment still has contracts — delete them first.")
