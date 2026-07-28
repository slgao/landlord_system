from fastapi import APIRouter, Depends, HTTPException
from db import fetch, execute, execute_returning
from auth import require_auth
from api.schemas.building import BuildingIn, BuildingOut

router = APIRouter(prefix="/buildings", tags=["Buildings"])

_COLS = "id, name, street, house_no, zip, city, notes"


def _row(r, unit_count=0) -> BuildingOut:
    return BuildingOut(id=r[0], name=r[1], street=r[2], house_no=r[3],
                       zip=r[4], city=r[5], notes=r[6], unit_count=unit_count)


@router.get("/", response_model=list[BuildingOut])
def list_buildings(owner: int = Depends(require_auth)):
    rows = fetch("""
        SELECT b.id, b.name, b.street, b.house_no, b.zip, b.city, b.notes,
               COUNT(p.id)
        FROM buildings b
        LEFT JOIN properties p ON p.building_id = b.id AND p.owner_id = b.owner_id
        WHERE b.owner_id = ?
        GROUP BY b.id
        ORDER BY b.name NULLS LAST, b.id
    """, (owner,))
    return [_row(r, r[7]) for r in rows]


@router.get("/{building_id}", response_model=BuildingOut)
def get_building(building_id: int, owner: int = Depends(require_auth)):
    rows = fetch(f"SELECT {_COLS} FROM buildings WHERE id=? AND owner_id=?", (building_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Building not found")
    cnt = fetch("SELECT COUNT(*) FROM properties WHERE building_id=? AND owner_id=?",
                (building_id, owner))[0][0]
    return _row(rows[0], cnt)


@router.post("/", response_model=BuildingOut, status_code=201)
def create_building(body: BuildingIn, owner: int = Depends(require_auth)):
    bid = execute_returning(
        "INSERT INTO buildings (name, street, house_no, zip, city, notes, owner_id) "
        "VALUES (?,?,?,?,?,?,?) RETURNING id",
        (body.name, body.street, body.house_no, body.zip, body.city, body.notes, owner),
    )[0][0]
    return get_building(bid, owner)


@router.put("/{building_id}", response_model=BuildingOut)
def update_building(building_id: int, body: BuildingIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM buildings WHERE id=? AND owner_id=?", (building_id, owner)):
        raise HTTPException(status_code=404, detail="Building not found")
    execute(
        "UPDATE buildings SET name=?, street=?, house_no=?, zip=?, city=?, notes=? "
        "WHERE id=? AND owner_id=?",
        (body.name, body.street, body.house_no, body.zip, body.city, body.notes, building_id, owner),
    )
    return get_building(building_id, owner)


@router.delete("/{building_id}", status_code=204)
def delete_building(building_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM buildings WHERE id=? AND owner_id=?", (building_id, owner)):
        raise HTTPException(status_code=404, detail="Building not found")
    # Properties keep existing; their building_id is set NULL by the FK.
    execute("DELETE FROM buildings WHERE id=? AND owner_id=?", (building_id, owner))
