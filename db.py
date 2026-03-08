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
        name TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS tenants(
        id INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS contracts(
        id INTEGER PRIMARY KEY,
        tenant_id INTEGER,
        apartment_id INTEGER,
        rent REAL,
        start_date TEXT
    )
    """)

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
