#! /usr/bin/env python
# coding=utf-8
# ================================================================
#   Copyright (C) 2026 * Ltd. All rights reserved.
#
#   Editor      : EMACS
#   File name   : db.py
#   Author      : slgao
#   Created date: Sun Mar 08 2026 16:20:20
#   Description : PostgreSQL backend (migrated from SQLite)
#
# ================================================================

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def _adapt(query: str) -> str:
    """Convert SQLite-style syntax to PostgreSQL / psycopg2-compatible syntax.
    - Escape literal % → %% so psycopg2 doesn't treat them as format specifiers
    - ? placeholders → %s
    - date('now') → CURRENT_DATE::TEXT  (TEXT so it compares cleanly with TEXT columns)
    Order matters: escape % first, then add %s placeholders.
    """
    return (
        query
        .replace("%", "%%")
        .replace("?", "%s")
        .replace("date('now')", "CURRENT_DATE::TEXT")
    )


def _normalize(rows):
    """Convert Decimal → float in every cell so existing arithmetic works unchanged.
    PostgreSQL returns NUMERIC columns as decimal.Decimal; SQLite returned float."""
    from decimal import Decimal
    return [
        tuple(float(v) if isinstance(v, Decimal) else v for v in row)
        for row in rows
    ]


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS properties(
        id      SERIAL PRIMARY KEY,
        name    TEXT,
        address TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS apartments(
        id          SERIAL PRIMARY KEY,
        property_id INTEGER,
        name        TEXT,
        flat        TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS tenants(
        id     SERIAL PRIMARY KEY,
        name   TEXT,
        email  TEXT,
        gender TEXT DEFAULT 'diverse'
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS contracts(
        id                      SERIAL PRIMARY KEY,
        tenant_id               INTEGER,
        apartment_id            INTEGER,
        rent                    NUMERIC(10,2),
        start_date              TEXT,
        end_date                TEXT,
        kaution_amount          NUMERIC(10,2),
        kaution_paid_date       TEXT,
        kaution_returned_date   TEXT,
        kaution_returned_amount NUMERIC(10,2),
        terminated              INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id           SERIAL PRIMARY KEY,
        contract_id  INTEGER,
        amount       NUMERIC(10,2),
        payment_date TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS kaution_deductions(
        id             SERIAL PRIMARY KEY,
        contract_id    INTEGER NOT NULL,
        date           TEXT,
        amount         NUMERIC(10,2),
        category       TEXT,
        reason         TEXT,
        reference_type TEXT,
        reference_id   INTEGER
    )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS ix_kaution_deductions_contract_id "
        "ON kaution_deductions(contract_id)"
    )

    c.execute("""
    CREATE TABLE IF NOT EXISTS flat_costs(
        id           SERIAL PRIMARY KEY,
        apartment_id INTEGER,
        cost_type    TEXT,
        amount       NUMERIC(10,2),
        frequency    TEXT,
        valid_from   TEXT,
        valid_to     TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS reminders(
        id           SERIAL PRIMARY KEY,
        contract_id  INTEGER,
        sent_date    TEXT,
        months_due   TEXT,
        amount_due   NUMERIC(10,2),
        channel      TEXT,
        note         TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS heizung_meters(
        id                SERIAL PRIMARY KEY,
        apartment_id      INTEGER,
        serial_number     TEXT,
        description       TEXT,
        unit_price        NUMERIC(10,4) DEFAULT 0.0,
        unit_label        TEXT DEFAULT 'Einheiten',
        conversion_factor NUMERIC(10,4) DEFAULT 1.0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS gas_meters(
        id           SERIAL PRIMARY KEY,
        apartment_id INTEGER NOT NULL,
        serial_number TEXT,
        description  TEXT,
        z_zahl       NUMERIC(10,4) DEFAULT 1.0,
        brennwert    NUMERIC(10,4) DEFAULT 10.0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS strom_meters(
        id            SERIAL PRIMARY KEY,
        apartment_id  INTEGER NOT NULL,
        serial_number TEXT,
        description   TEXT
    )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS ix_strom_meters_apartment_id "
        "ON strom_meters(apartment_id)"
    )

    c.execute("""
    CREATE TABLE IF NOT EXISTS wasser_meters(
        id            SERIAL PRIMARY KEY,
        apartment_id  INTEGER NOT NULL,
        serial_number TEXT,
        description   TEXT,
        type          TEXT NOT NULL DEFAULT 'kalt'
    )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS ix_wasser_meters_apartment_id "
        "ON wasser_meters(apartment_id)"
    )

    c.execute("""
    CREATE TABLE IF NOT EXISTS meter_readings(
        id           SERIAL PRIMARY KEY,
        meter_type   TEXT          NOT NULL,
        meter_id     INTEGER       NOT NULL,
        reading_date TEXT          NOT NULL,
        reading      NUMERIC(12,3) NOT NULL,
        note         TEXT
    )
    """)
    c.execute(
        "CREATE INDEX IF NOT EXISTS ix_meter_readings_meter "
        "ON meter_readings(meter_type, meter_id, reading_date)"
    )

    c.execute("""
    CREATE TABLE IF NOT EXISTS co_tenants(
        id          SERIAL PRIMARY KEY,
        contract_id INTEGER NOT NULL,
        name        TEXT NOT NULL,
        gender      TEXT DEFAULT 'diverse',
        email       TEXT,
        in_contract INTEGER DEFAULT 0
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS billing_profiles(
        id           SERIAL PRIMARY KEY,
        tenant_id    INTEGER,
        label        TEXT,
        created_date TEXT,
        data         TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS config(
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    conn.commit()
    conn.close()


def get_config(key, default=None):
    rows = fetch("SELECT value FROM config WHERE key=?", (key,))
    return rows[0][0] if rows else default


def set_config(key, value):
    execute(
        "INSERT INTO config (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (key, value)
    )


def insert(table, values):
    conn = get_conn()
    c = conn.cursor()
    placeholders = ",".join(["%s"] * len(values))
    c.execute(
        f"INSERT INTO {table} VALUES (DEFAULT,{placeholders})",
        values
    )
    conn.commit()
    conn.close()


def delete(table, entry_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"DELETE FROM {table} WHERE id = %s", (entry_id,))
    conn.commit()
    conn.close()


def fetch(query, params=()):
    conn = get_conn()
    c = conn.cursor()
    c.execute(_adapt(query), params)
    rows = _normalize(c.fetchall())
    conn.close()
    return rows


def execute(query, params=()):
    conn = get_conn()
    c = conn.cursor()
    c.execute(_adapt(query), params)
    conn.commit()
    conn.close()


def get_tenant_address(tenant_name):
    """Return property address for a tenant via their active contract, or None."""
    rows = fetch("""
        SELECT p.address
        FROM contracts c
        JOIN tenants t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE t.name = ?
        LIMIT 1
    """, (tenant_name,))
    return rows[0][0] if rows else None


def get_tenant_gender(tenant_name):
    rows = fetch("SELECT gender FROM tenants WHERE name = ? LIMIT 1", (tenant_name,))
    return rows[0][0] if rows else "diverse"
