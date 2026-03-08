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


def init_db():

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        address TEXT,
        tenants_in_flat INTEGER
    )
    """)

    conn.commit()
    conn.close()


def add_tenant(name, address, tenants):

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute(
        "INSERT INTO tenants (name,address,tenants_in_flat) VALUES (?,?,?)",
        (name, address, tenants),
    )

    conn.commit()
    conn.close()


def get_tenants():

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT * FROM tenants")

    rows = c.fetchall()

    conn.close()

    return rows
