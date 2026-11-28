from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from db import fetch, execute, execute_returning, fetch_bundle
from auth import require_auth
from api.schemas.apartment import ApartmentIn, ApartmentOut
from rent_periods import RentSchedule
from tenancy_history import build as build_history

router = APIRouter(prefix="/apartments", tags=["Apartments"])


_SELECT = """
    SELECT a.id, a.property_id, p.name, a.name, a.flat, a.size_sqm
    FROM apartments a JOIN properties p ON a.property_id = p.id
"""


def _row(r) -> ApartmentOut:
    return ApartmentOut(id=r[0], property_id=r[1], property_name=r[2], name=r[3],
                        flat=r[4], size_sqm=float(r[5]) if r[5] is not None else None)


@router.get("/", response_model=list[ApartmentOut])
def list_apartments(property_id: int | None = None, owner: int = Depends(require_auth)):
    if property_id:
        rows = fetch(f"{_SELECT} WHERE a.property_id=? AND a.owner_id=? ORDER BY a.flat, a.name",
                     (property_id, owner))
    else:
        rows = fetch(f"{_SELECT} WHERE a.owner_id=? ORDER BY p.name, a.flat, a.name", (owner,))
    return [_row(r) for r in rows]


@router.get("/{apartment_id}", response_model=ApartmentOut)
def get_apartment(apartment_id: int, owner: int = Depends(require_auth)):
    rows = fetch(f"{_SELECT} WHERE a.id=? AND a.owner_id=?", (apartment_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return _row(rows[0])


# Six independent reads, one round trip. The deposit figures prefer the
# kaution_returns ledger and fall back to the legacy columns on the contract,
# which is where returns were recorded before that table existed.
_HISTORY_PARTS = (
    ("unit", """
        SELECT json_build_array(a.id, a.property_id, p.name, a.name, a.flat,
                                a.size_sqm)
        FROM apartments a JOIN properties p ON p.id = a.property_id
        WHERE a.id = ? AND a.owner_id = ?
    """),
    # Rooms are siblings when they share (property_id, flat) — the grouping
    # /contracts/{id}/occupancy uses. A unit with no flat label has none.
    ("siblings", """
        SELECT json_build_array(s.id, s.name, s.size_sqm)
        FROM apartments s, apartments me
        WHERE me.id = ? AND me.owner_id = ?
          AND s.owner_id = me.owner_id AND s.property_id = me.property_id
          AND s.id <> me.id AND COALESCE(me.flat, '') <> ''
          AND COALESCE(s.flat, '') = COALESCE(me.flat, '')
        ORDER BY s.name
    """),
    ("tenancies", """
        SELECT json_build_array(
            c.id, c.tenant_id, t.name, c.start_date, c.end_date,
            COALESCE(c.terminated, 0),
            c.kaution_amount, COALESCE(c.kaution_currency, 'EUR'),
            COALESCE((SELECT SUM(amount) FROM kaution_returns
                      WHERE contract_id = c.id), c.kaution_returned_amount),
            COALESCE((SELECT MAX(date) FROM kaution_returns
                      WHERE contract_id = c.id), c.kaution_returned_date))
        FROM contracts c LEFT JOIN tenants t ON t.id = c.tenant_id
        WHERE c.apartment_id = ? AND c.owner_id = ?
    """),
    ("rents", """
        SELECT json_build_array(r.contract_id, r.valid_from, r.rent,
                                r.nebenkosten_vorauszahlung)
        FROM contract_rents r JOIN contracts c ON c.id = r.contract_id
        WHERE c.apartment_id = ? AND r.owner_id = ?
        ORDER BY r.valid_from
    """),
    ("co_tenants", """
        SELECT json_build_array(ct.contract_id, ct.name,
                                COALESCE(ct.in_contract, 0))
        FROM co_tenants ct JOIN contracts c ON c.id = ct.contract_id
        WHERE c.apartment_id = ? AND ct.owner_id = ?
        ORDER BY ct.name
    """),
    ("handovers", """
        SELECT json_build_array(h.contract_id, h.kind, h.date,
                                COALESCE(h.signed, 0))
        FROM handover_protocols h JOIN contracts c ON c.id = h.contract_id
        WHERE c.apartment_id = ? AND h.owner_id = ?
        ORDER BY h.date
    """),
)


@router.get("/{apartment_id}/tenancies")
def apartment_tenancies(apartment_id: int, owner: int = Depends(require_auth)):
    """Every tenant this flat or WG room has had, and the gaps between them.

    The unit's own history only: a WG room's siblings come back under
    `siblings` as context, never folded into the timeline, because each room
    is let on its own contract and has its own vacancy.
    """
    loaded = fetch_bundle([(name, sql, (apartment_id, owner))
                           for name, sql in _HISTORY_PARTS])
    if not loaded["unit"]:
        raise HTTPException(status_code=404, detail="Apartment not found")
    unit = loaded["unit"][0]

    schedules: dict = {}
    for cid, valid_from, rent, nkv in loaded["rents"]:
        schedules.setdefault(cid, []).append((valid_from, rent, nkv))

    co_tenants: dict = {}
    for cid, name, in_contract in loaded["co_tenants"]:
        co_tenants.setdefault(cid, []).append(
            {"name": name, "in_contract": bool(in_contract)})

    handovers: dict = {}
    for cid, kind, when, signed in loaded["handovers"]:
        handovers.setdefault(cid, []).append(
            {"kind": kind, "date": when, "signed": bool(signed)})

    contracts = [{
        "contract_id": r[0], "tenant_id": r[1], "tenant_name": r[2],
        "start_date": r[3], "end_date": r[4], "terminated": r[5],
        "kaution_amount": r[6], "kaution_currency": r[7],
        "kaution_returned": r[8], "kaution_returned_date": r[9],
        "schedule": RentSchedule(schedules.get(r[0], ())),
        "co_tenants": co_tenants.get(r[0], []),
        "handovers": handovers.get(r[0], []),
    } for r in loaded["tenancies"]]

    history = build_history(contracts, date.today())
    return {
        "apartment": {"id": unit[0], "property_id": unit[1],
                      "property_name": unit[2], "name": unit[3],
                      "flat": unit[4],
                      "size_sqm": float(unit[5]) if unit[5] is not None else None},
        "siblings": [{"id": s[0], "name": s[1],
                      "size_sqm": float(s[2]) if s[2] is not None else None}
                     for s in loaded["siblings"]],
        **history,
    }


@router.post("/", response_model=ApartmentOut, status_code=201)
def create_apartment(body: ApartmentIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (body.property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    # Named columns, not db.insert(): that helper is positional and assumes
    # owner_id is the last column, which stopped being true the moment
    # size_sqm was added after it.
    new_id = execute_returning(
        "INSERT INTO apartments (property_id, name, flat, size_sqm, owner_id) "
        "VALUES (?,?,?,?,?) RETURNING id",
        (body.property_id, body.name, body.flat, body.size_sqm, owner))[0][0]
    return _row(fetch(f"{_SELECT} WHERE a.id=?", (new_id,))[0])


@router.put("/{apartment_id}", response_model=ApartmentOut)
def update_apartment(apartment_id: int, body: ApartmentIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM apartments WHERE id=? AND owner_id=?", (apartment_id, owner)):
        raise HTTPException(status_code=404, detail="Apartment not found")
    if not fetch("SELECT id FROM properties WHERE id=? AND owner_id=?", (body.property_id, owner)):
        raise HTTPException(status_code=404, detail="Property not found")
    execute("UPDATE apartments SET property_id=?, name=?, flat=?, size_sqm=? "
            "WHERE id=? AND owner_id=?",
            (body.property_id, body.name, body.flat, body.size_sqm, apartment_id, owner))
    return _row(fetch(f"{_SELECT} WHERE a.id=?", (apartment_id,))[0])


@router.delete("/{apartment_id}", status_code=204)
def delete_apartment(apartment_id: int, owner: int = Depends(require_auth)):
    import psycopg2.errors
    if not fetch("SELECT id FROM apartments WHERE id=? AND owner_id=?", (apartment_id, owner)):
        raise HTTPException(status_code=404, detail="Apartment not found")
    try:
        execute("DELETE FROM apartments WHERE id=? AND owner_id=?", (apartment_id, owner))
    except psycopg2.errors.ForeignKeyViolation:
        raise HTTPException(status_code=409,
                            detail="Apartment still has contracts — delete them first.")
