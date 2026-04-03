#! /usr/bin/env python
# coding=utf-8
# ================================================================
#   Copyright (C) 2026 * Ltd. All rights reserved.
#
#   Editor      : EMACS
#   File name   : database.py
#   Author      : slgao
#   Created date: Sun Mar 08 2026 16:20:20
#   Description :
#
# ================================================================

import sqlite3
from pathlib import Path

DB_PATH = Path("data/landlord.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

def init_db():

    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS properties(
        id INTEGER PRIMARY KEY,
        name TEXT,
        address TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS apartments(
        id INTEGER PRIMARY KEY,
        property_id INTEGER,
        name TEXT,
        flat TEXT
    )
    """)
    try:
        c.execute("ALTER TABLE apartments ADD COLUMN flat TEXT")
        conn.commit()
    except Exception:
        pass

    c.execute("""
    CREATE TABLE IF NOT EXISTS tenants(
        id INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT,
        gender TEXT DEFAULT 'diverse'
    )
    """)
    # migrate existing db
    try:
        c.execute("ALTER TABLE tenants ADD COLUMN gender TEXT DEFAULT 'diverse'")
        conn.commit()
    except Exception:
        pass

    c.execute("""
    CREATE TABLE IF NOT EXISTS contracts(
        id INTEGER PRIMARY KEY,
        tenant_id INTEGER,
        apartment_id INTEGER,
        rent REAL,
        start_date TEXT,
        end_date TEXT,
        kaution_amount REAL,
        kaution_paid_date TEXT,
        kaution_returned_date TEXT,
        kaution_returned_amount REAL
    )
    """)
    for col, typ in [
        ("kaution_amount", "REAL"),
        ("kaution_paid_date", "TEXT"),
        ("kaution_returned_date", "TEXT"),
        ("kaution_returned_amount", "REAL"),
    ]:
        try:
            c.execute(f"ALTER TABLE contracts ADD COLUMN {col} {typ}")
            conn.commit()
        except Exception:
            pass

    c.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY,
        contract_id INTEGER,
        amount REAL,
        payment_date TEXT
    )
    """)

    conn.commit()
    conn.close()


def insert(table, values):

    conn = get_conn()
    c = conn.cursor()

    placeholders = ",".join(["?"]*len(values))

    c.execute(
        f"INSERT INTO {table} VALUES (NULL,{placeholders})",
        values
    )

    conn.commit()
    conn.close()

def delete(table, entry_id):
    conn = get_conn()
    c = conn.cursor()
    
    c.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
    
    conn.commit()
    conn.close()

def fetch(query, params=()):

    conn = get_conn()
    c = conn.cursor()

    c.execute(query, params)
    rows = c.fetchall()

    conn.close()

    return rows


def execute(query, params=()):

    conn = get_conn()
    c = conn.cursor()

    c.execute(query, params)
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
