from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import fetch, execute, execute_returning
from auth import require_auth

router = APIRouter(prefix="/meters", tags=["Meters"])


def _own_apartment(apartment_id: int, owner: int):
    if not fetch("SELECT id FROM apartments WHERE id=? AND owner_id=?", (apartment_id, owner)):
        raise HTTPException(404, "Apartment not found")


# ── Strom ────────────────────────────────────────────────────────────────────

class StromMeterIn(BaseModel):
    apartment_id: int
    serial_number: Optional[str] = None
    description: Optional[str] = None
    scope: str = "shared"


class StromMeterOut(BaseModel):
    id: int
    apartment_id: int
    apartment_name: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    scope: str


_STROM_SEL = """
    SELECT sm.id, sm.apartment_id, a.name,
           sm.serial_number, sm.description, COALESCE(sm.scope,'shared')
    FROM strom_meters sm JOIN apartments a ON a.id=sm.apartment_id
"""


def _strom(r):
    return StromMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                         serial_number=r[3], description=r[4], scope=r[5])


@router.get("/strom", response_model=list[StromMeterOut])
def list_strom_meters(apartment_id: int | None = None, owner: int = Depends(require_auth)):
    if apartment_id:
        rows = fetch(f"{_STROM_SEL} WHERE sm.apartment_id=? AND sm.owner_id=? ORDER BY a.name",
                     (apartment_id, owner))
    else:
        rows = fetch(f"{_STROM_SEL} WHERE sm.owner_id=? ORDER BY a.name", (owner,))
    return [_strom(r) for r in rows]


@router.post("/strom", response_model=StromMeterOut, status_code=201)
def create_strom_meter(body: StromMeterIn, owner: int = Depends(require_auth)):
    _own_apartment(body.apartment_id, owner)
    nid = execute_returning(
        "INSERT INTO strom_meters (apartment_id,serial_number,description,scope,owner_id) "
        "VALUES (?,?,?,?,?) RETURNING id",
        (body.apartment_id, body.serial_number, body.description, body.scope, owner))[0][0]
    return _strom(fetch(f"{_STROM_SEL} WHERE sm.id=?", (nid,))[0])


@router.put("/strom/{meter_id}", response_model=StromMeterOut)
def update_strom_meter(meter_id: int, body: StromMeterIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM strom_meters WHERE id=? AND owner_id=?", (meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    _own_apartment(body.apartment_id, owner)
    execute("UPDATE strom_meters SET apartment_id=?, serial_number=?, description=?, scope=? "
            "WHERE id=? AND owner_id=?",
            (body.apartment_id, body.serial_number, body.description, body.scope, meter_id, owner))
    return _strom(fetch(f"{_STROM_SEL} WHERE sm.id=?", (meter_id,))[0])


@router.delete("/strom/{meter_id}", status_code=204)
def delete_strom_meter(meter_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM strom_meters WHERE id=? AND owner_id=?", (meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    execute("DELETE FROM meter_readings WHERE meter_type='strom' AND meter_id=? AND owner_id=?",
            (meter_id, owner))
    execute("DELETE FROM strom_meters WHERE id=? AND owner_id=?", (meter_id, owner))


# ── Gas ──────────────────────────────────────────────────────────────────────

class GasMeterIn(BaseModel):
    apartment_id: int
    serial_number: Optional[str] = None
    description: Optional[str] = None
    z_zahl: float = 1.0
    brennwert: float = 10.0
    scope: str = "shared"


class GasMeterOut(BaseModel):
    id: int
    apartment_id: int
    apartment_name: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    z_zahl: float
    brennwert: float
    scope: str


_GAS_SEL = """
    SELECT gm.id, gm.apartment_id, a.name, gm.serial_number, gm.description,
           gm.z_zahl, gm.brennwert, COALESCE(gm.scope,'shared')
    FROM gas_meters gm JOIN apartments a ON a.id=gm.apartment_id
"""


def _gas(r):
    return GasMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                       serial_number=r[3], description=r[4],
                       z_zahl=float(r[5]), brennwert=float(r[6]), scope=r[7])


@router.get("/gas", response_model=list[GasMeterOut])
def list_gas_meters(apartment_id: int | None = None, owner: int = Depends(require_auth)):
    if apartment_id:
        rows = fetch(f"{_GAS_SEL} WHERE gm.apartment_id=? AND gm.owner_id=? ORDER BY a.name",
                     (apartment_id, owner))
    else:
        rows = fetch(f"{_GAS_SEL} WHERE gm.owner_id=? ORDER BY a.name", (owner,))
    return [_gas(r) for r in rows]


@router.post("/gas", response_model=GasMeterOut, status_code=201)
def create_gas_meter(body: GasMeterIn, owner: int = Depends(require_auth)):
    _own_apartment(body.apartment_id, owner)
    nid = execute_returning(
        "INSERT INTO gas_meters (apartment_id,serial_number,description,z_zahl,brennwert,scope,owner_id) "
        "VALUES (?,?,?,?,?,?,?) RETURNING id",
        (body.apartment_id, body.serial_number, body.description,
         body.z_zahl, body.brennwert, body.scope, owner))[0][0]
    return _gas(fetch(f"{_GAS_SEL} WHERE gm.id=?", (nid,))[0])


@router.put("/gas/{meter_id}", response_model=GasMeterOut)
def update_gas_meter(meter_id: int, body: GasMeterIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM gas_meters WHERE id=? AND owner_id=?", (meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    _own_apartment(body.apartment_id, owner)
    execute("""
        UPDATE gas_meters SET apartment_id=?, serial_number=?, description=?,
               z_zahl=?, brennwert=?, scope=? WHERE id=? AND owner_id=?
    """, (body.apartment_id, body.serial_number, body.description,
          body.z_zahl, body.brennwert, body.scope, meter_id, owner))
    return _gas(fetch(f"{_GAS_SEL} WHERE gm.id=?", (meter_id,))[0])


@router.delete("/gas/{meter_id}", status_code=204)
def delete_gas_meter(meter_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM gas_meters WHERE id=? AND owner_id=?", (meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    execute("DELETE FROM meter_readings WHERE meter_type='gas' AND meter_id=? AND owner_id=?",
            (meter_id, owner))
    execute("DELETE FROM gas_meters WHERE id=? AND owner_id=?", (meter_id, owner))


# ── Wasser ───────────────────────────────────────────────────────────────────

class WasserMeterIn(BaseModel):
    apartment_id: int
    serial_number: Optional[str] = None
    description: Optional[str] = None
    type: str = "kalt"
    scope: str = "shared"


class WasserMeterOut(BaseModel):
    id: int
    apartment_id: int
    apartment_name: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    type: str
    scope: str


_WASSER_SEL = """
    SELECT wm.id, wm.apartment_id, a.name, wm.serial_number, wm.description,
           wm.type, COALESCE(wm.scope,'shared')
    FROM wasser_meters wm JOIN apartments a ON a.id=wm.apartment_id
"""


def _wasser(r):
    return WasserMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                          serial_number=r[3], description=r[4], type=r[5], scope=r[6])


@router.get("/wasser", response_model=list[WasserMeterOut])
def list_wasser_meters(apartment_id: int | None = None, owner: int = Depends(require_auth)):
    if apartment_id:
        rows = fetch(f"{_WASSER_SEL} WHERE wm.apartment_id=? AND wm.owner_id=? ORDER BY a.name, wm.type",
                     (apartment_id, owner))
    else:
        rows = fetch(f"{_WASSER_SEL} WHERE wm.owner_id=? ORDER BY a.name, wm.type", (owner,))
    return [_wasser(r) for r in rows]


@router.post("/wasser", response_model=WasserMeterOut, status_code=201)
def create_wasser_meter(body: WasserMeterIn, owner: int = Depends(require_auth)):
    _own_apartment(body.apartment_id, owner)
    nid = execute_returning(
        "INSERT INTO wasser_meters (apartment_id,serial_number,description,type,scope,owner_id) "
        "VALUES (?,?,?,?,?,?) RETURNING id",
        (body.apartment_id, body.serial_number, body.description, body.type, body.scope, owner))[0][0]
    return _wasser(fetch(f"{_WASSER_SEL} WHERE wm.id=?", (nid,))[0])


@router.put("/wasser/{meter_id}", response_model=WasserMeterOut)
def update_wasser_meter(meter_id: int, body: WasserMeterIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM wasser_meters WHERE id=? AND owner_id=?", (meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    _own_apartment(body.apartment_id, owner)
    execute("""
        UPDATE wasser_meters SET apartment_id=?, serial_number=?, description=?,
               type=?, scope=? WHERE id=? AND owner_id=?
    """, (body.apartment_id, body.serial_number, body.description,
          body.type, body.scope, meter_id, owner))
    return _wasser(fetch(f"{_WASSER_SEL} WHERE wm.id=?", (meter_id,))[0])


@router.delete("/wasser/{meter_id}", status_code=204)
def delete_wasser_meter(meter_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM wasser_meters WHERE id=? AND owner_id=?", (meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    execute("DELETE FROM meter_readings WHERE meter_type='wasser' AND meter_id=? AND owner_id=?",
            (meter_id, owner))
    execute("DELETE FROM wasser_meters WHERE id=? AND owner_id=?", (meter_id, owner))


# ── Heizung ──────────────────────────────────────────────────────────────────

class HeizungMeterIn(BaseModel):
    apartment_id: int
    serial_number: Optional[str] = None
    description: Optional[str] = None
    unit_price: float = 0.0
    unit_label: str = "Einheiten"
    conversion_factor: float = 1.0
    scope: str = "room"


class HeizungMeterOut(BaseModel):
    id: int
    apartment_id: int
    apartment_name: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    unit_price: float
    unit_label: str
    conversion_factor: float
    scope: str


_HEIZUNG_SEL = """
    SELECT hm.id, hm.apartment_id, a.name, hm.serial_number, hm.description,
           hm.unit_price, hm.unit_label, hm.conversion_factor, COALESCE(hm.scope,'room')
    FROM heizung_meters hm JOIN apartments a ON a.id=hm.apartment_id
"""


def _heizung(r):
    return HeizungMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                           serial_number=r[3], description=r[4],
                           unit_price=float(r[5]), unit_label=r[6],
                           conversion_factor=float(r[7]), scope=r[8])


@router.get("/heizung", response_model=list[HeizungMeterOut])
def list_heizung_meters(apartment_id: int | None = None, owner: int = Depends(require_auth)):
    if apartment_id:
        rows = fetch(f"{_HEIZUNG_SEL} WHERE hm.apartment_id=? AND hm.owner_id=? ORDER BY a.name",
                     (apartment_id, owner))
    else:
        rows = fetch(f"{_HEIZUNG_SEL} WHERE hm.owner_id=? ORDER BY a.name", (owner,))
    return [_heizung(r) for r in rows]


@router.post("/heizung", response_model=HeizungMeterOut, status_code=201)
def create_heizung_meter(body: HeizungMeterIn, owner: int = Depends(require_auth)):
    _own_apartment(body.apartment_id, owner)
    nid = execute_returning(
        "INSERT INTO heizung_meters (apartment_id,serial_number,description,unit_price,"
        "unit_label,conversion_factor,scope,owner_id) VALUES (?,?,?,?,?,?,?,?) RETURNING id",
        (body.apartment_id, body.serial_number, body.description, body.unit_price,
         body.unit_label, body.conversion_factor, body.scope, owner))[0][0]
    return _heizung(fetch(f"{_HEIZUNG_SEL} WHERE hm.id=?", (nid,))[0])


@router.put("/heizung/{meter_id}", response_model=HeizungMeterOut)
def update_heizung_meter(meter_id: int, body: HeizungMeterIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM heizung_meters WHERE id=? AND owner_id=?", (meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    _own_apartment(body.apartment_id, owner)
    execute("""
        UPDATE heizung_meters SET apartment_id=?, serial_number=?, description=?,
               unit_price=?, unit_label=?, conversion_factor=?, scope=? WHERE id=? AND owner_id=?
    """, (body.apartment_id, body.serial_number, body.description,
          body.unit_price, body.unit_label, body.conversion_factor, body.scope, meter_id, owner))
    return _heizung(fetch(f"{_HEIZUNG_SEL} WHERE hm.id=?", (meter_id,))[0])


@router.delete("/heizung/{meter_id}", status_code=204)
def delete_heizung_meter(meter_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM heizung_meters WHERE id=? AND owner_id=?", (meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    execute("DELETE FROM meter_readings WHERE meter_type='heizung' AND meter_id=? AND owner_id=?",
            (meter_id, owner))
    execute("DELETE FROM heizung_meters WHERE id=? AND owner_id=?", (meter_id, owner))



# ── Meters relevant to one apartment (WG-aware) ──────────────────────────────
# A WG is modelled as one `apartments` row per room, all sharing the same
# property_id + `flat` value. The flat's Strom/Gas/Wasser meters are registered
# on whichever room happened to be entered first, so asking for "the meters of
# room 1" by apartment_id alone returns nothing for the other two rooms — which
# is why a WG Übergabeprotokoll came up with no Zählerstände at all.
#
# What a room actually needs is: everything shared by its flat, plus whatever is
# metered per room — and the `scope` column already says which is which
# ('shared' by default for Strom/Gas/Wasser, 'room' for a Heizkostenverteiler).


def meter_belongs_to_room(meter_apartment_id: int, scope: str | None,
                          room_apartment_id: int) -> bool:
    """Should this meter appear on `room_apartment_id`'s protocol?

    Your own meters always count, whatever their scope — a room-scoped
    Heizkostenverteiler is yours precisely because it is registered on you.
    A sibling room's meter counts only if it is shared, which is what keeps
    each room's own Heizkostenverteiler off its flatmates' sheets.
    """
    if meter_apartment_id == room_apartment_id:
        return True
    return (scope or "shared") == "shared"


class ApartmentMeterOut(BaseModel):
    meter_type: str
    id: int
    apartment_id: int
    apartment_name: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    scope: str
    # False when the meter is registered on a flatmate's room rather than this
    # one — the UI says so, because the landlord did not enter it here.
    own: bool


_TYPE_SELECTS = {
    "strom":   "SELECT id, apartment_id, serial_number, description, COALESCE(scope,'shared') FROM strom_meters",
    "gas":     "SELECT id, apartment_id, serial_number, description, COALESCE(scope,'shared') FROM gas_meters",
    "wasser":  "SELECT id, apartment_id, serial_number, COALESCE(description, type), COALESCE(scope,'shared') FROM wasser_meters",
    "heizung": "SELECT id, apartment_id, serial_number, description, COALESCE(scope,'room')   FROM heizung_meters",
}


@router.get("/for-apartment", response_model=list[ApartmentMeterOut])
def meters_for_apartment(apartment_id: int, owner: int = Depends(require_auth)):
    """Every meter a given room should be read for, across all four types."""
    row = fetch("SELECT property_id, flat FROM apartments WHERE id=? AND owner_id=?",
                (apartment_id, owner))
    if not row:
        raise HTTPException(404, "Apartment not found")
    property_id, flat = row[0]

    # The rooms of this flat. A blank `flat` means the apartment stands alone —
    # grouping those together would pool every unassigned apartment in the
    # building into one imaginary shared flat.
    if flat:
        siblings = fetch("SELECT id, name FROM apartments "
                         "WHERE property_id=? AND flat=? AND owner_id=?",
                         (property_id, flat, owner))
    else:
        siblings = fetch("SELECT id, name FROM apartments WHERE id=? AND owner_id=?",
                         (apartment_id, owner))
    names = {r[0]: r[1] for r in siblings}
    if not names:
        return []

    out: list[ApartmentMeterOut] = []
    for mtype, sel in _TYPE_SELECTS.items():
        placeholders = ",".join("?" for _ in names)
        rows = fetch(f"{sel} WHERE apartment_id IN ({placeholders}) AND owner_id=? ORDER BY id",
                     (*names.keys(), owner))
        for r in rows:
            if not meter_belongs_to_room(r[1], r[4], apartment_id):
                continue
            out.append(ApartmentMeterOut(
                meter_type=mtype, id=r[0], apartment_id=r[1],
                apartment_name=names.get(r[1]), serial_number=r[2],
                description=r[3], scope=r[4], own=(r[1] == apartment_id),
            ))
    return out

# ── Meter Readings ────────────────────────────────────────────────────────────

_METER_TABLES = {"strom": "strom_meters", "gas": "gas_meters",
                 "wasser": "wasser_meters", "heizung": "heizung_meters"}


class MeterReadingIn(BaseModel):
    meter_type: str
    meter_id: int
    reading_date: str
    reading: float
    note: Optional[str] = None


class MeterReadingOut(BaseModel):
    id: int
    meter_type: str
    meter_id: int
    reading_date: str
    reading: float
    note: Optional[str] = None
    # The handovers this reading was taken at, e.g. ["Auszug · Zhenwu Wei",
    # "Einzug · Yunkun Rui"]. A same-day changeover reads the meter once, and
    # this is what says so instead of the page showing the observation twice.
    taken_at: list[str] = []


@router.get("/readings", response_model=list[MeterReadingOut])
def list_readings(meter_type: str | None = None, meter_id: int | None = None,
                  owner: int = Depends(require_auth)):
    conditions, params = ["owner_id=?"], [owner]
    if meter_type:
        conditions.append("meter_type=?"); params.append(meter_type)
    if meter_id:
        conditions.append("meter_id=?"); params.append(meter_id)
    where = "WHERE " + " AND ".join(conditions)
    rows = fetch(f"""
        SELECT id, meter_type, meter_id, reading_date, reading, note
        FROM meter_readings {where}
        ORDER BY reading_date DESC, id DESC
    """, tuple(params))
    if not rows:
        return []

    # One query for the whole page rather than one per reading.
    links = fetch("""
        SELECT mrp.reading_id, p.kind, t.name
        FROM meter_reading_protocols mrp
        JOIN handover_protocols p ON p.id = mrp.protocol_id
        LEFT JOIN contracts c ON c.id = p.contract_id
        LEFT JOIN tenants   t ON t.id = c.tenant_id
        WHERE mrp.owner_id=? ORDER BY p.date, p.id
    """, (owner,))
    from api.routers.handover import protocol_label
    taken: dict[int, list[str]] = {}
    for reading_id, kind, tenant in links:
        taken.setdefault(reading_id, []).append(protocol_label(kind, tenant))

    return [MeterReadingOut(id=r[0], meter_type=r[1], meter_id=r[2],
                            reading_date=r[3], reading=float(r[4]), note=r[5],
                            taken_at=taken.get(r[0], [])) for r in rows]


@router.post("/readings", response_model=MeterReadingOut, status_code=201)
def create_reading(body: MeterReadingIn, owner: int = Depends(require_auth)):
    table = _METER_TABLES.get(body.meter_type)
    if not table:
        raise HTTPException(422, "Unknown meter_type")
    if not fetch(f"SELECT id FROM {table} WHERE id=? AND owner_id=?", (body.meter_id, owner)):
        raise HTTPException(404, "Meter not found")
    nid = execute_returning("""
        INSERT INTO meter_readings (meter_type, meter_id, reading_date, reading, note, owner_id)
        VALUES (?,?,?,?,?,?) RETURNING id
    """, (body.meter_type, body.meter_id, body.reading_date, body.reading, body.note, owner))[0][0]
    return MeterReadingOut(id=nid, meter_type=body.meter_type, meter_id=body.meter_id,
                           reading_date=body.reading_date, reading=body.reading, note=body.note)


@router.delete("/readings/{reading_id}", status_code=204)
def delete_reading(reading_id: int, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM meter_readings WHERE id=? AND owner_id=?", (reading_id, owner)):
        raise HTTPException(404, "Reading not found")
    execute("DELETE FROM meter_readings WHERE id=? AND owner_id=?", (reading_id, owner))
