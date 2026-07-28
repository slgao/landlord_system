from fastapi import APIRouter, HTTPException
from db import fetch, execute, execute_returning
from api.schemas.building import BuildingIn, BuildingOut

router = APIRouter(prefix="/buildings", tags=["Buildings"])

_COLS = "id, name, street, house_no, zip, city, notes"


def _row(r, unit_count=0) -> BuildingOut:
    return BuildingOut(id=r[0], name=r[1], street=r[2], house_no=r[3],
                       zip=r[4], city=r[5], notes=r[6], unit_count=unit_count)


@router.get("/", response_model=list[BuildingOut])
def list_buildings():
    rows = fetch("""
        SELECT b.id, b.name, b.street, b.house_no, b.zip, b.city, b.notes,
               COUNT(p.id)
        FROM buildings b
        LEFT JOIN properties p ON p.building_id = b.id
        GROUP BY b.id
        ORDER BY b.name NULLS LAST, b.id
    """)
    return [_row(r, r[7]) for r in rows]


@router.get("/{building_id}", response_model=BuildingOut)
def get_building(building_id: int):
    rows = fetch(f"SELECT {_COLS} FROM buildings WHERE id=?", (building_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Building not found")
    cnt = fetch("SELECT COUNT(*) FROM properties WHERE building_id=?", (building_id,))[0][0]
    return _row(rows[0], cnt)


@router.post("/", response_model=BuildingOut, status_code=201)
def create_building(body: BuildingIn):
    bid = execute_returning(
        "INSERT INTO buildings (name, street, house_no, zip, city, notes) "
        "VALUES (?,?,?,?,?,?) RETURNING id",
        (body.name, body.street, body.house_no, body.zip, body.city, body.notes),
    )[0][0]
    return get_building(bid)


@router.put("/{building_id}", response_model=BuildingOut)
def update_building(building_id: int, body: BuildingIn):
    if not fetch("SELECT id FROM buildings WHERE id=?", (building_id,)):
        raise HTTPException(status_code=404, detail="Building not found")
    execute(
        "UPDATE buildings SET name=?, street=?, house_no=?, zip=?, city=?, notes=? WHERE id=?",
        (body.name, body.street, body.house_no, body.zip, body.city, body.notes, building_id),
    )
    return get_building(building_id)


@router.delete("/{building_id}", status_code=204)
def delete_building(building_id: int):
    if not fetch("SELECT id FROM buildings WHERE id=?", (building_id,)):
        raise HTTPException(status_code=404, detail="Building not found")
    # Properties keep existing; their building_id is set NULL by the FK.
    execute("DELETE FROM buildings WHERE id=?", (building_id,))
