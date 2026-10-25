"""Everything this landlord has entered, in one file.

A self-hosted tool holding ten years of records has to answer "can I get my
data out" before anyone can reasonably commit to it, and §147 AO requires the
records behind a tax return to stay readable for ten years — which is not a
promise a running Postgres container makes on its own.

So: one request, one JSON document, every table scoped to the caller. It is
the backup, the thing to hand an accountant, and the thing to read when this
application is no longer around.

Stored PDFs are left out deliberately. They are bytes, they dominate the size
by orders of magnitude, and each already has an endpoint of its own; the rows
here carry `has_pdf` so nothing is silently missing.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from auth import require_auth
from db import fetch

router = APIRouter(prefix="/export", tags=["Export"])

# Every owner-scoped table, with the columns to write. Listed rather than
# discovered so a new table has to be added deliberately — an export that
# silently skips a table is worse than no export at all, and one that silently
# includes a column of decrypted secrets is worse still.
TABLES: dict[str, str] = {
    "properties": "id, name, address, tax_relevant, building_id, we_label, mea, "
                  "market_value, market_value_date, owned, living_sqm, plot_sqm, "
                  "comparable_per_sqm, valuation_note",
    "buildings": "id, name, street, house_no, zip, city, notes",
    "apartments": "id, property_id, name, flat, size_sqm",
    "tenants": "id, name, gender, email, phone",
    "contracts": "id, tenant_id, apartment_id, currency, start_date, end_date, "
                 "kaution_amount, kaution_currency, kaution_paid_date, "
                 "kaution_returned_date, kaution_returned_amount, terminated, "
                 "rent_settled_until, nk_mode",
    "contract_rents": "id, contract_id, valid_from, rent, nebenkosten_vorauszahlung, "
                      "kind, note",
    "co_tenants": "id, contract_id, name, gender, email, in_contract",
    "payments": "id, contract_id, amount, payment_date, currency, orig_amount, "
                "orig_currency, kind, settlement_id",
    "flat_costs": "id, apartment_id, cost_type, amount, frequency, valid_from, valid_to",
    "expenses": "id, property_id, apartment_id, expense_date, amount, category, "
                "vendor, note, deductible, distribute_years, source_file, utility, "
                "period_start, period_end, bill_total, tenant_settled, "
                "(pdf IS NOT NULL) AS has_pdf",
    "mortgages": "id, property_id, label, principal, interest_rate_pct, "
                 "tilgung_rate_pct, start_date, note, fixed_until, follow_up_rate_pct",
    "property_tax_profiles": "id, property_id, purchase_date, purchase_price, "
                             "purchase_costs, building_share_pct, afa_rate_pct",
    "tax_year_overrides": "id, property_id, tax_year, field, value, note",
    "nk_settlements": "id, contract_id, period_start, period_end, amount, "
                      "issued_date, note, (pdf IS NOT NULL) AS has_pdf",
    "nk_settlement_bills": "id, settlement_id, expense_id",
    "kaution_payments": "id, contract_id, date, amount, note",
    "kaution_deductions": "id, contract_id, date, amount, category, reason, "
                          "reference_type, reference_id",
    "kaution_returns": "id, contract_id, date, amount, note",
    "meter_readings": "id, meter_type, meter_id, reading_date, reading, note",
    "strom_meters": "id, apartment_id, serial_number, description, scope",
    "gas_meters": "id, apartment_id, serial_number, description, z_zahl, brennwert, scope",
    "wasser_meters": "id, apartment_id, serial_number, description, type, scope",
    "heizung_meters": "id, apartment_id, serial_number, description, unit_price, "
                      "unit_label, conversion_factor, scope",
    "handover_protocols": "id, contract_id, kind, date, note, signed_tenant, signed_landlord",
    "protocol_items": "id, protocol_id, kind, area, condition, quantity, "
                      "estimated_cost, note, sort_order",
    "meter_reading_protocols": "id, reading_id, protocol_id",
    "reminders": "id, contract_id, sent_date, months_due, amount_due",
    "billing_profiles": "id, tenant_id, label, created_date, data",
    "land_values": "id, property_id, year, brw, gfz, east, north, source, fetched_at",
}

# `config` is deliberately absent: it holds the SMTP password, encrypted with
# a key that is not in the export. Writing it out would either leak a secret
# or produce an unreadable blob, and neither belongs in a backup a landlord
# forwards to their accountant.


def _json_default(v):
    from decimal import Decimal
    if isinstance(v, Decimal):
        # As a string: a JSON number would turn 1050.25 into a float, and this
        # file is meant to still be exact in ten years.
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None
    return str(v)


def collect(owner: int) -> dict:
    """Every row this landlord owns, table by table."""
    data: dict = {}
    for table, columns in TABLES.items():
        try:
            rows = fetch(f"SELECT {columns} FROM {table} WHERE owner_id = ? ORDER BY id",
                         (owner,))
        except Exception:
            # A table a deployment has not migrated to yet is absent, not fatal:
            # an export that fails whole because of one missing table is no
            # export. Its absence is visible in the file.
            continue
        names = [c.strip().split(" AS ")[-1].strip() for c in columns.split(",")]
        data[table] = [dict(zip(names, row)) for row in rows]
    return data


@router.get("/")
def export_everything(owner: int = Depends(require_auth)):
    """The whole portfolio as one JSON document, offered as a download."""
    import json
    payload = {
        "format": "dachly-export",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "note": "Stored PDFs are not included; rows that have one carry has_pdf. "
                "Settings are not included, because they hold an encrypted secret.",
        "data": collect(owner),
    }
    body = json.dumps(payload, default=_json_default, ensure_ascii=False, indent=1)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=body, media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="dachly-export-{stamp}.json"'})


def _count_sql(tables) -> str:
    """One statement that counts them all.

    A loop of COUNT(*) is twenty-nine statements for a single line of text —
    about a second of waiting against a database 38 ms away, to say "7 rows".
    As scalar subqueries it is one round trip, and each still costs the same
    index scan it did before.
    """
    parts = ", ".join(f"(SELECT COUNT(*) FROM {t} WHERE owner_id=?)" for t in tables)
    return f"SELECT {parts}"


@router.get("/summary")
def export_summary(owner: int = Depends(require_auth)):
    """How many rows the export would hold, per table — so the page can say
    what is about to be downloaded instead of just offering a button."""
    tables = list(TABLES)
    try:
        row = fetch(_count_sql(tables), tuple(owner for _ in tables))[0]
        counts = {t: int(n) for t, n in zip(tables, row)}
    except Exception:
        # A deployment missing a table takes the whole statement down with it,
        # so fall back to asking one at a time and skipping what is absent.
        counts = {}
        for table in tables:
            try:
                counts[table] = int(fetch(
                    f"SELECT COUNT(*) FROM {table} WHERE owner_id=?", (owner,))[0][0])
            except Exception:
                continue
    return {"tables": counts, "rows": sum(counts.values())}
