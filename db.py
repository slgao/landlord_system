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

DB = "data/landlord.db"

def connect():
    return sqlite3.connect(DB)


def init_db():

    conn = connect()
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
        move_in DATE,
        move_out DATE
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS rent_payments(
        id INTEGER PRIMARY KEY,
        contract_id INTEGER,
        amount REAL,
        date DATE
    )
    """)

    conn.commit()
    conn.close()


def insert(table, values):

    conn = connect()
    c = conn.cursor()

    placeholders = ",".join(["?"]*len(values))

    c.execute(
        f"INSERT INTO {table} VALUES (NULL,{placeholders})",
        values
    )

    conn.commit()
    conn.close()


def fetch(query):

    conn = connect()
    c = conn.cursor()

    c.execute(query)
    rows = c.fetchall()

    conn.close()

    return rows
