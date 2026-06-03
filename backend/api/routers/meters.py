from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import fetch, execute, insert

router = APIRouter(prefix="/meters", tags=["Meters"])


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


@router.get("/strom", response_model=list[StromMeterOut])
def list_strom_meters(apartment_id: int | None = None):
    where = "WHERE sm.apartment_id=?" if apartment_id else ""
    params = (apartment_id,) if apartment_id else ()
    rows = fetch(f"""
        SELECT sm.id, sm.apartment_id, a.name,
               sm.serial_number, sm.description, COALESCE(sm.scope,'shared')
        FROM strom_meters sm JOIN apartments a ON a.id=sm.apartment_id
        {where} ORDER BY a.name
    """, params)
    return [StromMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                          serial_number=r[3], description=r[4], scope=r[5]) for r in rows]


@router.post("/strom", response_model=StromMeterOut, status_code=201)
def create_strom_meter(body: StromMeterIn):
    insert("strom_meters", (body.apartment_id, body.serial_number, body.description))
    rows = fetch("""
        SELECT sm.id, sm.apartment_id, a.name, sm.serial_number, sm.description, COALESCE(sm.scope,'shared')
        FROM strom_meters sm JOIN apartments a ON a.id=sm.apartment_id
        WHERE sm.apartment_id=? ORDER BY sm.id DESC LIMIT 1
    """, (body.apartment_id,))
    r = rows[0]
    return StromMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                         serial_number=r[3], description=r[4], scope=r[5])


@router.put("/strom/{meter_id}", response_model=StromMeterOut)
def update_strom_meter(meter_id: int, body: StromMeterIn):
    if not fetch("SELECT id FROM strom_meters WHERE id=?", (meter_id,)):
        raise HTTPException(404, "Meter not found")
    execute("UPDATE strom_meters SET apartment_id=?, serial_number=?, description=?, scope=? WHERE id=?",
            (body.apartment_id, body.serial_number, body.description, body.scope, meter_id))
    rows = fetch("""
        SELECT sm.id, sm.apartment_id, a.name, sm.serial_number, sm.description, COALESCE(sm.scope,'shared')
        FROM strom_meters sm JOIN apartments a ON a.id=sm.apartment_id WHERE sm.id=?
    """, (meter_id,))
    r = rows[0]
    return StromMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                         serial_number=r[3], description=r[4], scope=r[5])


@router.delete("/strom/{meter_id}", status_code=204)
def delete_strom_meter(meter_id: int):
    if not fetch("SELECT id FROM strom_meters WHERE id=?", (meter_id,)):
        raise HTTPException(404, "Meter not found")
    execute("DELETE FROM meter_readings WHERE meter_type='strom' AND meter_id=?", (meter_id,))
    execute("DELETE FROM strom_meters WHERE id=?", (meter_id,))


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


@router.get("/gas", response_model=list[GasMeterOut])
def list_gas_meters(apartment_id: int | None = None):
    where = "WHERE gm.apartment_id=?" if apartment_id else ""
    params = (apartment_id,) if apartment_id else ()
    rows = fetch(f"""
        SELECT gm.id, gm.apartment_id, a.name, gm.serial_number, gm.description,
               gm.z_zahl, gm.brennwert, COALESCE(gm.scope,'shared')
        FROM gas_meters gm JOIN apartments a ON a.id=gm.apartment_id
        {where} ORDER BY a.name
    """, params)
    return [GasMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                        serial_number=r[3], description=r[4],
                        z_zahl=float(r[5]), brennwert=float(r[6]), scope=r[7]) for r in rows]


@router.post("/gas", response_model=GasMeterOut, status_code=201)
def create_gas_meter(body: GasMeterIn):
    insert("gas_meters", (body.apartment_id, body.serial_number, body.description,
                          body.z_zahl, body.brennwert))
    rows = fetch("""
        SELECT gm.id, gm.apartment_id, a.name, gm.serial_number, gm.description,
               gm.z_zahl, gm.brennwert, COALESCE(gm.scope,'shared')
        FROM gas_meters gm JOIN apartments a ON a.id=gm.apartment_id
        WHERE gm.apartment_id=? ORDER BY gm.id DESC LIMIT 1
    """, (body.apartment_id,))
    r = rows[0]
    return GasMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                       serial_number=r[3], description=r[4],
                       z_zahl=float(r[5]), brennwert=float(r[6]), scope=r[7])


@router.put("/gas/{meter_id}", response_model=GasMeterOut)
def update_gas_meter(meter_id: int, body: GasMeterIn):
    if not fetch("SELECT id FROM gas_meters WHERE id=?", (meter_id,)):
        raise HTTPException(404, "Meter not found")
    execute("""
        UPDATE gas_meters SET apartment_id=?, serial_number=?, description=?,
               z_zahl=?, brennwert=?, scope=? WHERE id=?
    """, (body.apartment_id, body.serial_number, body.description,
          body.z_zahl, body.brennwert, body.scope, meter_id))
    rows = fetch("""
        SELECT gm.id, gm.apartment_id, a.name, gm.serial_number, gm.description,
               gm.z_zahl, gm.brennwert, COALESCE(gm.scope,'shared')
        FROM gas_meters gm JOIN apartments a ON a.id=gm.apartment_id WHERE gm.id=?
    """, (meter_id,))
    r = rows[0]
    return GasMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                       serial_number=r[3], description=r[4],
                       z_zahl=float(r[5]), brennwert=float(r[6]), scope=r[7])


@router.delete("/gas/{meter_id}", status_code=204)
def delete_gas_meter(meter_id: int):
    if not fetch("SELECT id FROM gas_meters WHERE id=?", (meter_id,)):
        raise HTTPException(404, "Meter not found")
    execute("DELETE FROM meter_readings WHERE meter_type='gas' AND meter_id=?", (meter_id,))
    execute("DELETE FROM gas_meters WHERE id=?", (meter_id,))


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


@router.get("/wasser", response_model=list[WasserMeterOut])
def list_wasser_meters(apartment_id: int | None = None):
    where = "WHERE wm.apartment_id=?" if apartment_id else ""
    params = (apartment_id,) if apartment_id else ()
    rows = fetch(f"""
        SELECT wm.id, wm.apartment_id, a.name, wm.serial_number, wm.description,
               wm.type, COALESCE(wm.scope,'shared')
        FROM wasser_meters wm JOIN apartments a ON a.id=wm.apartment_id
        {where} ORDER BY a.name, wm.type
    """, params)
    return [WasserMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                           serial_number=r[3], description=r[4],
                           type=r[5], scope=r[6]) for r in rows]


@router.post("/wasser", response_model=WasserMeterOut, status_code=201)
def create_wasser_meter(body: WasserMeterIn):
    insert("wasser_meters", (body.apartment_id, body.serial_number, body.description, body.type))
    rows = fetch("""
        SELECT wm.id, wm.apartment_id, a.name, wm.serial_number, wm.description,
               wm.type, COALESCE(wm.scope,'shared')
        FROM wasser_meters wm JOIN apartments a ON a.id=wm.apartment_id
        WHERE wm.apartment_id=? ORDER BY wm.id DESC LIMIT 1
    """, (body.apartment_id,))
    r = rows[0]
    return WasserMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                          serial_number=r[3], description=r[4], type=r[5], scope=r[6])


@router.put("/wasser/{meter_id}", response_model=WasserMeterOut)
def update_wasser_meter(meter_id: int, body: WasserMeterIn):
    if not fetch("SELECT id FROM wasser_meters WHERE id=?", (meter_id,)):
        raise HTTPException(404, "Meter not found")
    execute("""
        UPDATE wasser_meters SET apartment_id=?, serial_number=?, description=?,
               type=?, scope=? WHERE id=?
    """, (body.apartment_id, body.serial_number, body.description,
          body.type, body.scope, meter_id))
    rows = fetch("""
        SELECT wm.id, wm.apartment_id, a.name, wm.serial_number, wm.description,
               wm.type, COALESCE(wm.scope,'shared')
        FROM wasser_meters wm JOIN apartments a ON a.id=wm.apartment_id WHERE wm.id=?
    """, (meter_id,))
    r = rows[0]
    return WasserMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                          serial_number=r[3], description=r[4], type=r[5], scope=r[6])


@router.delete("/wasser/{meter_id}", status_code=204)
def delete_wasser_meter(meter_id: int):
    if not fetch("SELECT id FROM wasser_meters WHERE id=?", (meter_id,)):
        raise HTTPException(404, "Meter not found")
    execute("DELETE FROM meter_readings WHERE meter_type='wasser' AND meter_id=?", (meter_id,))
    execute("DELETE FROM wasser_meters WHERE id=?", (meter_id,))


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


@router.get("/heizung", response_model=list[HeizungMeterOut])
def list_heizung_meters(apartment_id: int | None = None):
    where = "WHERE hm.apartment_id=?" if apartment_id else ""
    params = (apartment_id,) if apartment_id else ()
    rows = fetch(f"""
        SELECT hm.id, hm.apartment_id, a.name, hm.serial_number, hm.description,
               hm.unit_price, hm.unit_label, hm.conversion_factor, COALESCE(hm.scope,'room')
        FROM heizung_meters hm JOIN apartments a ON a.id=hm.apartment_id
        {where} ORDER BY a.name
    """, params)
    return [HeizungMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                            serial_number=r[3], description=r[4],
                            unit_price=float(r[5]), unit_label=r[6],
                            conversion_factor=float(r[7]), scope=r[8]) for r in rows]


@router.post("/heizung", response_model=HeizungMeterOut, status_code=201)
def create_heizung_meter(body: HeizungMeterIn):
    insert("heizung_meters", (body.apartment_id, body.serial_number, body.description,
                              body.unit_price, body.unit_label, body.conversion_factor))
    rows = fetch("""
        SELECT hm.id, hm.apartment_id, a.name, hm.serial_number, hm.description,
               hm.unit_price, hm.unit_label, hm.conversion_factor, COALESCE(hm.scope,'room')
        FROM heizung_meters hm JOIN apartments a ON a.id=hm.apartment_id
        WHERE hm.apartment_id=? ORDER BY hm.id DESC LIMIT 1
    """, (body.apartment_id,))
    r = rows[0]
    return HeizungMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                           serial_number=r[3], description=r[4],
                           unit_price=float(r[5]), unit_label=r[6],
                           conversion_factor=float(r[7]), scope=r[8])


@router.put("/heizung/{meter_id}", response_model=HeizungMeterOut)
def update_heizung_meter(meter_id: int, body: HeizungMeterIn):
    if not fetch("SELECT id FROM heizung_meters WHERE id=?", (meter_id,)):
        raise HTTPException(404, "Meter not found")
    execute("""
        UPDATE heizung_meters SET apartment_id=?, serial_number=?, description=?,
               unit_price=?, unit_label=?, conversion_factor=?, scope=? WHERE id=?
    """, (body.apartment_id, body.serial_number, body.description,
          body.unit_price, body.unit_label, body.conversion_factor, body.scope, meter_id))
    rows = fetch("""
        SELECT hm.id, hm.apartment_id, a.name, hm.serial_number, hm.description,
               hm.unit_price, hm.unit_label, hm.conversion_factor, COALESCE(hm.scope,'room')
        FROM heizung_meters hm JOIN apartments a ON a.id=hm.apartment_id WHERE hm.id=?
    """, (meter_id,))
    r = rows[0]
    return HeizungMeterOut(id=r[0], apartment_id=r[1], apartment_name=r[2],
                           serial_number=r[3], description=r[4],
                           unit_price=float(r[5]), unit_label=r[6],
                           conversion_factor=float(r[7]), scope=r[8])


@router.delete("/heizung/{meter_id}", status_code=204)
def delete_heizung_meter(meter_id: int):
    if not fetch("SELECT id FROM heizung_meters WHERE id=?", (meter_id,)):
        raise HTTPException(404, "Meter not found")
    execute("DELETE FROM meter_readings WHERE meter_type='heizung' AND meter_id=?", (meter_id,))
    execute("DELETE FROM heizung_meters WHERE id=?", (meter_id,))


# ── Meter Readings ────────────────────────────────────────────────────────────

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


@router.get("/readings", response_model=list[MeterReadingOut])
def list_readings(meter_type: str | None = None, meter_id: int | None = None):
    conditions, params = [], []
    if meter_type:
        conditions.append("meter_type=?"); params.append(meter_type)
    if meter_id:
        conditions.append("meter_id=?"); params.append(meter_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    rows = fetch(f"""
        SELECT id, meter_type, meter_id, reading_date, reading, note
        FROM meter_readings {where}
        ORDER BY reading_date DESC, id DESC
    """, tuple(params))
    return [MeterReadingOut(id=r[0], meter_type=r[1], meter_id=r[2],
                            reading_date=r[3], reading=float(r[4]), note=r[5]) for r in rows]


@router.post("/readings", response_model=MeterReadingOut, status_code=201)
def create_reading(body: MeterReadingIn):
    from db import get_conn, put_conn
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO meter_readings (meter_type, meter_id, reading_date, reading, note)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (body.meter_type, body.meter_id, body.reading_date, body.reading, body.note))
        new_id = c.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    return MeterReadingOut(id=new_id, meter_type=body.meter_type, meter_id=body.meter_id,
                           reading_date=body.reading_date, reading=body.reading, note=body.note)


@router.delete("/readings/{reading_id}", status_code=204)
def delete_reading(reading_id: int):
    if not fetch("SELECT id FROM meter_readings WHERE id=?", (reading_id,)):
        raise HTTPException(404, "Reading not found")
    execute("DELETE FROM meter_readings WHERE id=?", (reading_id,))
