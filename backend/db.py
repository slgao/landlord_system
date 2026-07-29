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
import contextvars
import psycopg2
from psycopg2 import pool as _pg_pool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# Request-scoped current owner (user id). Set by auth.require_auth for every
# authenticated request; read by insert() to stamp owner_id, and available to
# routers that scope their reads. None outside a request (e.g. migrations).
_current_owner: "contextvars.ContextVar[int | None]" = contextvars.ContextVar(
    "current_owner", default=None)


def set_current_owner(owner_id: int | None) -> None:
    _current_owner.set(owner_id)


def current_owner() -> int | None:
    return _current_owner.get()


def require_owner() -> int:
    """Owner id for the current request, or raise if unset (a programming error:
    a data query ran outside an authenticated request)."""
    o = _current_owner.get()
    if o is None:
        raise RuntimeError("No current owner set — data access outside an authenticated request")
    return o

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
    """Pass-through. PostgreSQL returns NUMERIC as decimal.Decimal — we keep
    that precision for accounting (item 1a from the code review)."""
    return [tuple(row) for row in rows]


_migration_done = False

def migrate_to_head() -> None:
    """Run `alembic upgrade head` once per process. Guarded by a module-level
    flag so repeated calls in the same process are no-ops."""
    global _migration_done
    if _migration_done:
        return
    from alembic.config import Config
    from alembic import command
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
    command.upgrade(Config(cfg_path), "head")
    _migration_done = True



def get_config(key, default=None):
    """Per-user config read, scoped to the current request's owner."""
    rows = fetch("SELECT value FROM config WHERE key=? AND owner_id=?",
                 (key, current_owner()))
    return rows[0][0] if rows else default


def set_config(key, value):
    owner = require_owner()
    execute(
        "INSERT INTO config (key, value, owner_id) VALUES (?, ?, ?) "
        "ON CONFLICT (owner_id, key) DO UPDATE SET value = EXCLUDED.value",
        (key, value, owner)
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
    """Positional insert into an owner-scoped table. Stamps owner_id (the last
    column on every owned table) from the current request's owner and returns
    the generated id. All callers operate on owner-scoped tables."""
    owner = require_owner()
    conn = get_conn()
    try:
        c = conn.cursor()
        placeholders = ",".join(["%s"] * len(values))
        # owner_id is the trailing column on every owned table (see the
        # add_users_and_owner_id migration).
        c.execute(
            f"INSERT INTO {table} VALUES (DEFAULT,{placeholders},%s) RETURNING id",
            (*values, owner),
        )
        new_id = c.fetchone()[0]
        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


def delete(table, entry_id):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(f"DELETE FROM {table} WHERE id = %s", (entry_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


# Errors that mean the pooled connection is dead/stale (server closed it after
# an idle timeout, the DB restarted, the TCP link dropped, …). When we hit one
# we must DISCARD the connection instead of returning it to the pool — otherwise
# the broken connection keeps getting handed out and poisons later requests.
_CONN_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


def _run_once(query, params, commit, returning=False):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(_adapt(query), params)
        # `returning` fetches the RETURNING rows before committing so callers get
        # the generated id/values back from a writing statement.
        result = _normalize(c.fetchall()) if (returning or not commit) else None
        if commit:
            conn.commit()
        else:
            # End the read's implicit transaction before the connection returns
            # to the pool. psycopg2 opens a transaction on the first statement;
            # without this the pooled connection sits "idle in transaction" and
            # keeps a stale MVCC snapshot, so a later request on the same
            # connection could read data frozen at this point in time.
            conn.rollback()
    except _CONN_ERRORS:
        # Evict the dead connection so the pool replaces it on the next getconn().
        try:
            _get_pool().putconn(conn, close=True)
        except Exception:
            pass
        raise
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        put_conn(conn)
        raise
    else:
        put_conn(conn)
        return result


def fetch(query, params=()):
    try:
        return _run_once(query, params, commit=False)
    except _CONN_ERRORS:
        # The stale connection was evicted above; retry once with a fresh one.
        return _run_once(query, params, commit=False)


def execute(query, params=()):
    try:
        _run_once(query, params, commit=True)
    except _CONN_ERRORS:
        _run_once(query, params, commit=True)


def execute_returning(query, params=()):
    """Run a writing statement with a RETURNING clause, commit, and return the
    returned rows (e.g. `INSERT ... RETURNING id`). Use this instead of fetch()
    for writes — fetch() never commits."""
    try:
        return _run_once(query, params, commit=True, returning=True)
    except _CONN_ERRORS:
        return _run_once(query, params, commit=True, returning=True)


def get_tenant_address(tenant_name):
    """Return property address for a tenant via their active contract, or None.
    Scoped to the current request's owner."""
    rows = fetch("""
        SELECT p.address
        FROM contracts c
        JOIN tenants t ON t.id = c.tenant_id
        JOIN apartments a ON a.id = c.apartment_id
        JOIN properties p ON p.id = a.property_id
        WHERE t.name = ? AND t.owner_id = ?
        LIMIT 1
    """, (tenant_name, current_owner()))
    return rows[0][0] if rows else None


def get_tenant_gender(tenant_name):
    rows = fetch("SELECT gender FROM tenants WHERE name = ? AND owner_id = ? LIMIT 1",
                 (tenant_name, current_owner()))
    return rows[0][0] if rows else "diverse"
