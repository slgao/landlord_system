from fastapi import APIRouter, HTTPException
from db import fetch, execute, execute_returning
from api.schemas.property import PropertyIn, PropertyOut

router = APIRouter(prefix="/properties", tags=["Properties"])

_SELECT = """
    SELECT p.id, p.name, p.address, p.building_id, p.we_label, p.mea, b.name
    FROM properties p
    LEFT JOIN buildings b ON b.id = p.building_id
"""


def _row(r) -> PropertyOut:
    return PropertyOut(id=r[0], name=r[1], address=r[2], building_id=r[3],
                       we_label=r[4], mea=float(r[5]) if r[5] is not None else None,
                       building_name=r[6])


@router.get("/", response_model=list[PropertyOut])
def list_properties():
    return [_row(r) for r in fetch(_SELECT + " ORDER BY p.name")]


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: int):
    rows = fetch(_SELECT + " WHERE p.id=?", (property_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Property not found")
    return _row(rows[0])


@router.post("/", response_model=PropertyOut, status_code=201)
def create_property(body: PropertyIn):
    pid = execute_returning(
        "INSERT INTO properties (name, address, building_id, we_label, mea) "
        "VALUES (?,?,?,?,?) RETURNING id",
        (body.name, body.address, body.building_id, body.we_label, body.mea),
    )[0][0]
    return get_property(pid)


@router.put("/{property_id}", response_model=PropertyOut)
def update_property(property_id: int, body: PropertyIn):
    if not fetch("SELECT id FROM properties WHERE id=?", (property_id,)):
        raise HTTPException(status_code=404, detail="Property not found")
    execute(
        "UPDATE properties SET name=?, address=?, building_id=?, we_label=?, mea=? WHERE id=?",
        (body.name, body.address, body.building_id, body.we_label, body.mea, property_id),
    )
    return get_property(property_id)


@router.delete("/{property_id}", status_code=204)
def delete_property(property_id: int):
    import psycopg2.errors
    if not fetch("SELECT id FROM properties WHERE id=?", (property_id,)):
        raise HTTPException(status_code=404, detail="Property not found")
    try:
        execute("DELETE FROM properties WHERE id=?", (property_id,))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(status_code=409,
                            detail="Property still has apartments — delete them first.")
