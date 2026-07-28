from fastapi import APIRouter, Depends, HTTPException
from db import fetch, execute, execute_returning, require_owner
from auth import require_auth
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


def _assert_building(building_id, owner):
    if building_id is not None and not fetch(
            "SELECT id FROM buildings WHERE id=? AND owner_id=?", (building_id, owner)):
        raise HTTPException(status_code=404, detail="Building not found")


@router.get("/", response_model=list[PropertyOut])
def list_properties(owner: int = Depends(require_auth)):
    return [_row(r) for r in fetch(_SELECT + " WHERE p.owner_id=? ORDER BY p.name", (owner,))]


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: int, owner: int = Depends(require_auth)):
    rows = fetch(_SELECT + " WHERE p.id=? AND p.owner_id=?", (property_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Property not found")
    return _row(rows[0])


@router.post("/", response_model=PropertyOut, status_code=201)
def create_property(body: PropertyIn, owner: int = Depends(require_auth)):
    _assert_building(body.building_id, owner)
    pid = execute_returning(
        "INSERT INTO properties (name, address, building_id, we_label, mea, owner_id) "
        "VALUES (?,?,?,?,?,?) RETURNING id",
        (body.name, body.address, body.building_id, body.we_label, body.mea, owner),
    )[0][0]
    return get_property(pid, owner)


@router.put("/{property_id}", response_model=PropertyOut)
def update_property(property_id: int, body: PropertyIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    _assert_building(body.building_id, owner)
    execute(
        "UPDATE properties SET name=?, address=?, building_id=?, we_label=?, mea=? "
        "WHERE id=? AND owner_id=?",
        (body.name, body.address, body.building_id, body.we_label, body.mea, property_id, owner),
    )
    return get_property(property_id, owner)


@router.delete("/{property_id}", status_code=204)
def delete_property(property_id: int, owner: int = Depends(require_auth)):
    import psycopg2.errors
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    try:
        execute("DELETE FROM properties WHERE id=? AND owner_id=?", (property_id, owner))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(status_code=409,
                            detail="Property still has apartments — delete them first.")
