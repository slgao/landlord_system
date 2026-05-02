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
from psycopg2 import pool as _pg_pool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

_POOL_MIN = int(os.environ.get("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.environ.get("DB_POOL_MAX", "10"))
_pool: _pg_pool.AbstractConnectionPool | None = None


def _get_pool() -> _pg_pool.AbstractConnectionPool:
    global _pool
    if _pool is None:
        _pool = _pg_pool.ThreadedConnectionPool(_POOL_MIN, _POOL_MAX, DATABASE_URL)
    return _pool


def get_conn():
    return _get_pool().getconn()


def put_conn(conn) -> None:
    _get_pool().putconn(conn)


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


def migrate_to_head() -> None:
    """Run `alembic upgrade head` programmatically. Idempotent."""
    from alembic.config import Config
    from alembic import command
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
    command.upgrade(Config(cfg_path), "head")



def get_config(key, default=None):
    rows = fetch("SELECT value FROM config WHERE key=?", (key,))
    return rows[0][0] if rows else default


def set_config(key, value):
    execute(
        "INSERT INTO config (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (key, value)
    )


def _fernet():
    """Return a Fernet instance if FERNET_KEY is set in the environment, else None."""
    key = os.environ.get("FERNET_KEY")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def get_secret_config(key, default=None):
    """Read a config value and decrypt it if FERNET_KEY is set."""
    value = get_config(key, default)
    if not value or value == default:
        return value
    f = _fernet()
    if f is None:
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception:
        return value  # legacy plaintext — return as-is


def set_secret_config(key, value):
    """Encrypt value with FERNET_KEY before storing, or store plaintext if key absent."""
    f = _fernet()
    if f and value:
        value = f.encrypt(value.encode()).decode()
    set_config(key, value)


def insert(table, values):
    conn = get_conn()
    try:
        c = conn.cursor()
        placeholders = ",".join(["%s"] * len(values))
        c.execute(
            f"INSERT INTO {table} VALUES (DEFAULT,{placeholders})",
            values
        )
        conn.commit()
    finally:
        put_conn(conn)


def delete(table, entry_id):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(f"DELETE FROM {table} WHERE id = %s", (entry_id,))
        conn.commit()
    finally:
        put_conn(conn)


def fetch(query, params=()):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(_adapt(query), params)
        return _normalize(c.fetchall())
    finally:
        put_conn(conn)


def execute(query, params=()):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(_adapt(query), params)
        conn.commit()
    finally:
        put_conn(conn)


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
