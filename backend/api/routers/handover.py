"""Wohnungsübergabeprotokoll — what was recorded when the keys changed hands.

Two protocols matter per tenancy: 'move_in' (Einzug) and 'move_out' (Auszug).
Each carries free notes, a list of findings (room conditions and keys), and the
Zählerstände read on the day.

The Zählerstände deliberately do not live here. They are written into
meter_readings — the same store the Nebenkostenabrechnung reads — and merely
linked to the protocols that witnessed them via meter_reading_protocols.
See the e2a9c4b17d53 and f4b6d82e05a1 migrations for why.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from db import fetch, execute, execute_returning
from auth import require_auth

router = APIRouter(prefix="/handover-protocols", tags=["Handover"])

KINDS = ("move_in", "move_out")
CONDITIONS = ("ok", "wear", "defect")
ITEM_KINDS = ("condition", "key")

# Mirrors _METER_TABLES in routers/meters.py — the four meter tables a reading
# can point at.
_METER_TABLES = {"strom": "strom_meters", "gas": "gas_meters",
                 "wasser": "wasser_meters", "heizung": "heizung_meters"}


# ── Models ───────────────────────────────────────────────────────────────────

class ProtocolIn(BaseModel):
    contract_id: int
    kind: str
    date: str
    time: Optional[str] = None
    present_persons: Optional[str] = None
    note: Optional[str] = None
    signed: bool = False


class ProtocolPatch(BaseModel):
    """Everything except contract_id/kind, which identify the protocol."""
    date: str
    time: Optional[str] = None
    present_persons: Optional[str] = None
    note: Optional[str] = None
    signed: bool = False


class ProtocolOut(BaseModel):
    id: int
    contract_id: int
    kind: str
    date: str
    time: Optional[str] = None
    present_persons: Optional[str] = None
    note: Optional[str] = None
    signed: bool = False
    # Rolled up so the contract page can show "3 Mängel · 245.00" without
    # fetching every item of every protocol.
    item_count: int = 0
    defect_count: int = 0
    defect_cost: float = 0.0
    reading_count: int = 0


class ItemIn(BaseModel):
    protocol_id: int
    kind: str = "condition"
    area: Optional[str] = None
    condition: Optional[str] = None
    quantity: Optional[int] = None
    estimated_cost: Optional[float] = None
    note: Optional[str] = None
    sort_order: int = 0


class ItemOut(BaseModel):
    id: int
    protocol_id: int
    kind: str
    area: Optional[str] = None
    condition: Optional[str] = None
    quantity: Optional[int] = None
    estimated_cost: Optional[float] = None
    note: Optional[str] = None
    sort_order: int = 0


class ProtocolReadingIn(BaseModel):
    meter_type: str
    meter_id: int
    reading: float
    note: Optional[str] = None


class ProtocolReadingOut(BaseModel):
    id: int
    meter_type: str
    meter_id: int
    reading_date: str
    reading: float
    note: Optional[str] = None
    # Denormalised for display, so the UI need not join four meter tables.
    serial_number: Optional[str] = None
    description: Optional[str] = None
    # Other handovers this same reading was taken at, e.g. ["Einzug · Yunkun Rui"].
    also_at: list[str] = []
    # True when this save joined an existing reading rather than creating one,
    # and the value already matched — so the UI can say it merged.
    merged: bool = False


# ── Helpers ──────────────────────────────────────────────────────────────────

_SELECT = """
    SELECT p.id, p.contract_id, p.kind, p.date, p.time, p.present_persons,
           p.note, COALESCE(p.signed, 0),
           (SELECT COUNT(*) FROM protocol_items i WHERE i.protocol_id = p.id),
           (SELECT COUNT(*) FROM protocol_items i
             WHERE i.protocol_id = p.id AND i.condition = 'defect'),
           COALESCE((SELECT SUM(i.estimated_cost) FROM protocol_items i
                      WHERE i.protocol_id = p.id AND i.condition = 'defect'), 0),
           (SELECT COUNT(*) FROM meter_reading_protocols mrp WHERE mrp.protocol_id = p.id)
    FROM handover_protocols p
"""


def _row(r) -> ProtocolOut:
    return ProtocolOut(
        id=r[0], contract_id=r[1], kind=r[2],
        date=r[3] if r[3] and r[3] != "None" else "",
        time=r[4] or None, present_persons=r[5], note=r[6], signed=bool(r[7]),
        item_count=int(r[8]), defect_count=int(r[9]),
        defect_cost=float(r[10] or 0), reading_count=int(r[11]),
    )


def _item_row(r) -> ItemOut:
    return ItemOut(id=r[0], protocol_id=r[1], kind=r[2], area=r[3], condition=r[4],
                   quantity=int(r[5]) if r[5] is not None else None,
                   estimated_cost=float(r[6]) if r[6] is not None else None,
                   note=r[7], sort_order=int(r[8] or 0))


def _own_contract(contract_id: int, owner: int):
    if not fetch("SELECT id FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner)):
        raise HTTPException(404, "Contract not found")


def _own_protocol(protocol_id: int, owner: int):
    rows = fetch("SELECT contract_id, date FROM handover_protocols WHERE id=? AND owner_id=?",
                 (protocol_id, owner))
    if not rows:
        raise HTTPException(404, "Protocol not found")
    return rows[0]


def _validate(kind: str, allowed, label: str):
    if kind not in allowed:
        raise HTTPException(422, f"Unknown {label}: {kind}")


def _require_date(d: str | None) -> str:
    """A protocol must be dated before it can hold Zählerstände.

    The readings are written into meter_readings with the protocol's date, and
    an undated reading is worse than a missing one: the Nebenkostenabrechnung
    interpolates between readings by date, so a blank would silently distort a
    bill rather than fail. ('None' is the legacy string this database uses for a
    missing date — see the backfill_none_string_dates migration.)
    """
    if not d or d == "None":
        raise HTTPException(422, "The protocol needs a date first")
    return d


# ── Protocols ────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ProtocolOut])
def list_protocols(contract_id: int | None = None, owner: int = Depends(require_auth)):
    if contract_id:
        rows = fetch(f"{_SELECT} WHERE p.contract_id=? AND p.owner_id=? ORDER BY p.date, p.id",
                     (contract_id, owner))
    else:
        rows = fetch(f"{_SELECT} WHERE p.owner_id=? ORDER BY p.date DESC, p.id DESC", (owner,))
    return [_row(r) for r in rows]


@router.get("/{protocol_id}", response_model=ProtocolOut)
def get_protocol(protocol_id: int, owner: int = Depends(require_auth)):
    rows = fetch(f"{_SELECT} WHERE p.id=? AND p.owner_id=?", (protocol_id, owner))
    if not rows:
        raise HTTPException(404, "Protocol not found")
    return _row(rows[0])


@router.post("/", response_model=ProtocolOut, status_code=201)
def create_protocol(body: ProtocolIn, owner: int = Depends(require_auth)):
    _validate(body.kind, KINDS, "kind")
    _require_date(body.date)
    _own_contract(body.contract_id, owner)
    new_id = execute_returning("""
        INSERT INTO handover_protocols
          (contract_id, kind, date, time, present_persons, note, signed, owner_id)
        VALUES (?,?,?,?,?,?,?,?) RETURNING id
    """, (body.contract_id, body.kind, body.date, body.time or None,
          body.present_persons, body.note, int(body.signed), owner))[0][0]
    return get_protocol(new_id, owner)


def _move_readings_to(protocol_id: int, new_date: str, owner: int) -> None:
    """Re-date this handover's Zählerstände when the handover itself is re-dated.

    A reading is dated by the meeting it was taken at, so a corrected protocol
    date has to carry its readings along — otherwise they sit at a date the
    meeting never happened on and the Nebenkostenabrechnung interpolates from it.

    Two things stop this being a plain UPDATE, and both would corrupt a
    neighbouring tenancy's record:

    - A reading shared with the other half of a same-day changeover belongs to
      that handover too. Dragging it would move a reading out from under a
      protocol whose date never changed, so it is left where it is and this
      protocol takes a reading at the new date instead.

    - Something may already stand at the new date for that meter. This protocol
      joins it rather than adding a second row for one observation — and joins it
      *without rewriting its value*, because the number there was recorded by
      whoever read the meter that day. Only an explicit save from the reading
      field changes a value.
    """
    rows = fetch("""
        SELECT m.id, m.meter_type, m.meter_id, m.reading, m.note,
               (SELECT COUNT(*) FROM meter_reading_protocols x WHERE x.reading_id = m.id)
        FROM meter_readings m
        JOIN meter_reading_protocols mrp ON mrp.reading_id = m.id
        WHERE mrp.protocol_id=? AND m.owner_id=?
    """, (protocol_id, owner))

    for rid, mtype, mid, value, note, holders in rows:
        target = fetch("""
            SELECT id FROM meter_readings
            WHERE meter_type=? AND meter_id=? AND reading_date=? AND owner_id=? AND id<>?
            ORDER BY id LIMIT 1
        """, (mtype, mid, new_date, owner, rid))

        # Nothing in the way and nobody else holding it: the reading simply moves.
        if not target and int(holders) <= 1:
            execute("UPDATE meter_readings SET reading_date=? WHERE id=? AND owner_id=?",
                    (new_date, rid, owner))
            continue

        execute("DELETE FROM meter_reading_protocols WHERE reading_id=? AND protocol_id=?",
                (rid, protocol_id))
        if target:
            new_id = target[0][0]
        else:
            # The note is deliberately not carried over: it describes the
            # observation being left behind ("Yunkun Rui - Einzugsablesung"), not
            # a new reading on a different day. Copying it would also make this
            # row look hand-annotated, and the cleanup below spares those.
            new_id = execute_returning("""
                INSERT INTO meter_readings
                  (meter_type, meter_id, reading_date, reading, note, owner_id)
                VALUES (?,?,?,?,NULL,?) RETURNING id
            """, (mtype, mid, new_date, value, owner))[0][0]
        if not fetch("SELECT id FROM meter_reading_protocols WHERE reading_id=? AND protocol_id=?",
                     (new_id, protocol_id)):
            execute("INSERT INTO meter_reading_protocols (reading_id, protocol_id, owner_id) "
                    "VALUES (?,?,?)", (new_id, protocol_id, owner))

        # The row this protocol just vacated: drop it only if no handover still
        # holds it and nobody wrote anything on it. A note means a human put it
        # there by hand on the Meter Readings page, and that is not ours to bin.
        orphaned = not fetch("SELECT 1 FROM meter_reading_protocols WHERE reading_id=?", (rid,))
        if orphaned and not (note or "").strip():
            execute("DELETE FROM meter_readings WHERE id=? AND owner_id=?", (rid, owner))


@router.put("/{protocol_id}", response_model=ProtocolOut)
def update_protocol(protocol_id: int, body: ProtocolPatch, owner: int = Depends(require_auth)):
    _own_protocol(protocol_id, owner)
    _require_date(body.date)
    execute("""
        UPDATE handover_protocols
        SET date=?, time=?, present_persons=?, note=?, signed=?
        WHERE id=? AND owner_id=?
    """, (body.date, body.time or None, body.present_persons, body.note,
          int(body.signed), protocol_id, owner))
    _move_readings_to(protocol_id, body.date, owner)
    return get_protocol(protocol_id, owner)


@router.delete("/{protocol_id}", status_code=204)
def delete_protocol(protocol_id: int, owner: int = Depends(require_auth)):
    _own_protocol(protocol_id, owner)
    # Items go with it (FK CASCADE), and so do its links to readings. The
    # readings themselves do not: they are billing data that outlives the
    # document, and one of them may still be held by the other handover of a
    # same-day changeover. They stay visible on the Meter Readings page.
    execute("DELETE FROM handover_protocols WHERE id=? AND owner_id=?", (protocol_id, owner))


# ── Items (conditions + keys) ────────────────────────────────────────────────

items_router = APIRouter(prefix="/protocol-items", tags=["Handover"])


@items_router.get("/", response_model=list[ItemOut])
def list_items(protocol_id: int, owner: int = Depends(require_auth)):
    rows = fetch("""
        SELECT id, protocol_id, kind, area, condition, quantity, estimated_cost, note, sort_order
        FROM protocol_items WHERE protocol_id=? AND owner_id=?
        ORDER BY kind DESC, sort_order, id
    """, (protocol_id, owner))
    return [_item_row(r) for r in rows]


@items_router.post("/", response_model=ItemOut, status_code=201)
def create_item(body: ItemIn, owner: int = Depends(require_auth)):
    _own_protocol(body.protocol_id, owner)
    _validate(body.kind, ITEM_KINDS, "item kind")
    if body.kind == "condition":
        _validate(body.condition or "ok", CONDITIONS, "condition")
    new_id = execute_returning("""
        INSERT INTO protocol_items
          (protocol_id, kind, area, condition, quantity, estimated_cost, note, sort_order, owner_id)
        VALUES (?,?,?,?,?,?,?,?,?) RETURNING id
    """, (body.protocol_id, body.kind, body.area,
          body.condition if body.kind == "condition" else None,
          body.quantity if body.kind == "key" else None,
          body.estimated_cost, body.note, body.sort_order, owner))[0][0]
    rows = fetch("SELECT id,protocol_id,kind,area,condition,quantity,estimated_cost,note,sort_order "
                 "FROM protocol_items WHERE id=?", (new_id,))
    return _item_row(rows[0])


@items_router.put("/{item_id}", response_model=ItemOut)
def update_item(item_id: int, body: ItemIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM protocol_items WHERE id=? AND owner_id=?", (item_id, owner)):
        raise HTTPException(404, "Item not found")
    _validate(body.kind, ITEM_KINDS, "item kind")
    if body.kind == "condition":
        _validate(body.condition or "ok", CONDITIONS, "condition")
    execute("""
        UPDATE protocol_items
        SET kind=?, area=?, condition=?, quantity=?, estimated_cost=?, note=?, sort_order=?
        WHERE id=? AND owner_id=?
    """, (body.kind, body.area,
          body.condition if body.kind == "condition" else None,
          body.quantity if body.kind == "key" else None,
          body.estimated_cost, body.note, body.sort_order, item_id, owner))
    rows = fetch("SELECT id,protocol_id,kind,area,condition,quantity,estimated_cost,note,sort_order "
                 "FROM protocol_items WHERE id=?", (item_id,))
    return _item_row(rows[0])


@items_router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM protocol_items WHERE id=? AND owner_id=?", (item_id, owner)):
        raise HTTPException(404, "Item not found")
    execute("DELETE FROM protocol_items WHERE id=? AND owner_id=?", (item_id, owner))


# ── Zählerstände ─────────────────────────────────────────────────────────────
# Readings taken at the handover. Stored in meter_readings so the
# Nebenkostenabrechnung sees them; meter_reading_protocols records which
# handovers witnessed each one.
#
# The invariant: one reading per meter per date. When a tenancy is handed
# straight on, the outgoing tenant's Auszug and the incoming tenant's Einzug are
# the same afternoon at the same meter — one observation, and two rows for it
# would leave the Nebenkostenabrechnung to choose between them.


def _reading_protocols(reading_id: int, owner: int):
    """Every handover this reading was taken at, oldest first."""
    return fetch("""
        SELECT p.id, p.kind, p.date, t.name
        FROM meter_reading_protocols mrp
        JOIN handover_protocols p ON p.id = mrp.protocol_id
        LEFT JOIN contracts c ON c.id = p.contract_id
        LEFT JOIN tenants   t ON t.id = c.tenant_id
        WHERE mrp.reading_id=? AND mrp.owner_id=?
        ORDER BY p.date, p.id
    """, (reading_id, owner))


def protocol_label(kind: str, tenant_name: str | None) -> str:
    """How a handover is named where a reading points back at it."""
    label = "Einzug" if kind == "move_in" else "Auszug"
    return f"{label} · {tenant_name}" if tenant_name else label


def same_reading_value(a: float, b: float) -> bool:
    """Whether two recorded values are the same number.

    Readings are Numeric(12,3), so an exact float comparison would call
    10229.000 and 10229.0 different and report a merge as a correction.
    """
    return abs(float(a) - float(b)) < 0.0005


def _attribution(reading_id: int, owner: int, exclude: int | None = None) -> list[str]:
    """Human labels for the other handovers sharing this reading, e.g.
    'Einzug · Yunkun Rui'. Shown wherever the reading appears, so a merged one
    says where it came from instead of looking like it was entered twice."""
    return [protocol_label(kind, tenant)
            for pid, kind, _date, tenant in _reading_protocols(reading_id, owner)
            if exclude is None or pid != exclude]


def _meter_meta(meter_type: str, meter_id: int):
    table = _METER_TABLES.get(meter_type)
    if not table:
        return (None, None)
    rows = fetch(f"SELECT serial_number, description FROM {table} WHERE id=?", (meter_id,))
    return (rows[0][0], rows[0][1]) if rows else (None, None)


@router.get("/{protocol_id}/readings", response_model=list[ProtocolReadingOut])
def list_protocol_readings(protocol_id: int, owner: int = Depends(require_auth)):
    _own_protocol(protocol_id, owner)
    rows = fetch("""
        SELECT m.id, m.meter_type, m.meter_id, m.reading_date, m.reading, m.note
        FROM meter_readings m
        JOIN meter_reading_protocols mrp ON mrp.reading_id = m.id
        WHERE mrp.protocol_id=? AND m.owner_id=?
        ORDER BY m.meter_type, m.meter_id
    """, (protocol_id, owner))
    out = []
    for r in rows:
        serial, desc = _meter_meta(r[1], r[2])
        out.append(ProtocolReadingOut(
            id=r[0], meter_type=r[1], meter_id=r[2], reading_date=r[3],
            reading=float(r[4]), note=r[5], serial_number=serial, description=desc,
            also_at=_attribution(r[0], owner, exclude=protocol_id),
        ))
    return out


@router.post("/{protocol_id}/readings", response_model=ProtocolReadingOut, status_code=201)
def add_protocol_reading(protocol_id: int, body: ProtocolReadingIn,
                         owner: int = Depends(require_auth)):
    _contract_id, prot_date = _own_protocol(protocol_id, owner)
    prot_date = _require_date(prot_date)
    table = _METER_TABLES.get(body.meter_type)
    if not table:
        raise HTTPException(422, "Unknown meter_type")
    if not fetch(f"SELECT id FROM {table} WHERE id=? AND owner_id=?", (body.meter_id, owner)):
        raise HTTPException(404, "Meter not found")

    # Adopt whatever already stands for this meter on this date, whoever wrote
    # it — the other handover of a same-day changeover, or the landlord typing it
    # on the Meter Readings page beforehand. Adding a second row instead is how
    # one observation ended up recorded three times.
    existing = fetch("""
        SELECT id, reading FROM meter_readings
        WHERE meter_type=? AND meter_id=? AND reading_date=? AND owner_id=?
        ORDER BY id LIMIT 1
    """, (body.meter_type, body.meter_id, prot_date, owner))

    if existing:
        rid, old_value = existing[0][0], float(existing[0][1])
        # A note the landlord wrote by hand stays; only overwrite it with one
        # actually supplied here.
        if body.note:
            execute("UPDATE meter_readings SET reading=?, note=? WHERE id=? AND owner_id=?",
                    (body.reading, body.note, rid, owner))
        else:
            execute("UPDATE meter_readings SET reading=? WHERE id=? AND owner_id=?",
                    (body.reading, rid, owner))
        merged = same_reading_value(old_value, body.reading)
    else:
        rid = execute_returning("""
            INSERT INTO meter_readings
              (meter_type, meter_id, reading_date, reading, note, owner_id)
            VALUES (?,?,?,?,?,?) RETURNING id
        """, (body.meter_type, body.meter_id, prot_date, body.reading,
              body.note, owner))[0][0]
        merged = False

    if not fetch("SELECT id FROM meter_reading_protocols WHERE reading_id=? AND protocol_id=?",
                 (rid, protocol_id)):
        execute("INSERT INTO meter_reading_protocols (reading_id, protocol_id, owner_id) "
                "VALUES (?,?,?)", (rid, protocol_id, owner))

    row = fetch("SELECT reading, note FROM meter_readings WHERE id=?", (rid,))[0]
    serial, desc = _meter_meta(body.meter_type, body.meter_id)
    return ProtocolReadingOut(
        id=rid, meter_type=body.meter_type, meter_id=body.meter_id,
        reading_date=prot_date, reading=float(row[0]), note=row[1],
        serial_number=serial, description=desc,
        also_at=_attribution(rid, owner, exclude=protocol_id),
        merged=bool(existing) and merged,
    )


@router.delete("/{protocol_id}/readings/{reading_id}", status_code=204)
def delete_protocol_reading(protocol_id: int, reading_id: int, owner: int = Depends(require_auth)):
    _own_protocol(protocol_id, owner)
    if not fetch("""SELECT 1 FROM meter_reading_protocols
                    WHERE reading_id=? AND protocol_id=? AND owner_id=?""",
                 (reading_id, protocol_id, owner)):
        raise HTTPException(404, "Reading not found")
    execute("DELETE FROM meter_reading_protocols WHERE reading_id=? AND protocol_id=? AND owner_id=?",
            (reading_id, protocol_id, owner))
    # Clearing it here retracts this handover's claim on the reading. The reading
    # itself only goes when no handover is left holding it — the other tenancy's
    # protocol, or a manual entry, still needs it.
    still_used = fetch("SELECT 1 FROM meter_reading_protocols WHERE reading_id=?", (reading_id,))
    if not still_used:
        execute("DELETE FROM meter_readings WHERE id=? AND owner_id=?", (reading_id, owner))


# ── PDF ──────────────────────────────────────────────────────────────────────

@router.get("/{protocol_id}/pdf")
def protocol_pdf(protocol_id: int, owner: int = Depends(require_auth)):
    """The signable document: take it to the flat, both parties sign it."""
    from pdfgen import uebergabeprotokoll_pdf
    from api.routers.reports import _landlord_name

    rows = fetch(f"{_SELECT} WHERE p.id=? AND p.owner_id=?", (protocol_id, owner))
    if not rows:
        raise HTTPException(404, "Protocol not found")
    prot = _row(rows[0])

    ctx = fetch("""
        SELECT t.name, a.name, p.name, p.address, c.start_date, c.end_date
        FROM contracts c
        JOIN tenants    t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE c.id=? AND c.owner_id=?
    """, (prot.contract_id, owner))
    tenant_name, apartment_name, property_name, address, start_date, end_date = (
        ctx[0] if ctx else ("", "", "", None, None, None))

    co = fetch("SELECT name FROM co_tenants WHERE contract_id=? AND owner_id=? ORDER BY id",
               (prot.contract_id, owner))

    items = list_items(protocol_id, owner)
    readings = list_protocol_readings(protocol_id, owner)

    pdf_bytes = uebergabeprotokoll_pdf(
        protocol=prot.model_dump(),
        tenant_name=tenant_name,
        co_tenant_names=[r[0] for r in co],
        apartment_name=apartment_name,
        property_name=property_name,
        address=address,
        conditions=[i.model_dump() for i in items if i.kind == "condition"],
        keys=[i.model_dump() for i in items if i.kind == "key"],
        readings=[r.model_dump() for r in readings],
        landlord_name=_landlord_name(),
    )
    kind_de = "Einzug" if prot.kind == "move_in" else "Auszug"
    safe = "".join(ch for ch in (tenant_name or "Mieter") if ch.isalnum() or ch in " -_").strip()
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="Uebergabeprotokoll_{kind_de}_{safe}.pdf"'})
