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

import re as _re
import os
import contextvars
import psycopg2
from psycopg2 import pool as _pg_pool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# Schema search_path enforced on every connection. Neon's pooler rejects the
# libpq `options` startup param and, in transaction pooling, discards a
# session-level SET across statements — so we can't rely on connect-time options
# or a one-off SET. We instead issue this as the first statement of each
# transaction (see get_conn), which keeps the app working even if the database
# role's default search_path is empty/misconfigured. Override via DB_SEARCH_PATH.
_SEARCH_PATH = os.environ.get("DB_SEARCH_PATH", '"$user", public')

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
# How long a request waits for a pooled connection before giving up. The pool
# raises immediately when every connection is checked out, and with ten
# connections against uvicorn's forty worker threads a dashboard load (four
# requests at once) could already trip that under a second visitor.
_POOL_WAIT_S = float(os.environ.get("DB_POOL_WAIT", "5"))
_pool: _pg_pool.AbstractConnectionPool | None = None


def _get_pool() -> _pg_pool.AbstractConnectionPool:
    global _pool
    if _pool is None:
        _pool = _pg_pool.ThreadedConnectionPool(_POOL_MIN, _POOL_MAX, DATABASE_URL)
    return _pool


def _checkout():
    """getconn() that waits (briefly) for a free connection instead of
    failing the request the instant the pool is fully checked out."""
    import time
    deadline = time.monotonic() + _POOL_WAIT_S
    while True:
        try:
            return _get_pool().getconn()
        except _pg_pool.PoolError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


# Whether we have to pin the search_path ourselves. Decided once, on the first
# connection, by asking the database whether an unqualified table already
# resolves under the role's own default.
#
# It usually does, and the check matters because the alternatives are all
# expensive or unavailable: the libpq `options` startup parameter is rejected
# by Neon's pooler, and a session-level SET cannot be relied on to survive
# transaction pooling — which left "SET on every checkout", a whole extra
# round trip on every single query. On a database 38 ms away that was the
# difference between a 193 ms fetch and a 37 ms one.
_needs_search_path: bool | None = None


def _probe_search_path(conn) -> bool:
    """True when unqualified names do NOT resolve, so we must set the path."""
    try:
        with conn.cursor() as c:
            # to_regclass returns NULL when the name is not visible on the
            # current path. `config` exists from the baseline migration on.
            c.execute("SELECT to_regclass('config') IS NULL")
            return bool(c.fetchone()[0])
    except Exception:
        return True                    # unsure: keep the safe, slower behaviour


def get_conn():
    global _needs_search_path
    conn = _checkout()
    try:
        # Autocommit: every call here runs exactly one statement, so a
        # transaction adds a BEGIN and a COMMIT/ROLLBACK round trip and buys
        # nothing. It also means a pooled connection can never sit "idle in
        # transaction" holding a stale snapshot, which the read path used to
        # roll back by hand.
        if not conn.autocommit:
            conn.autocommit = True
        if _needs_search_path is None:
            _needs_search_path = _probe_search_path(conn)
        if _needs_search_path:
            # _SEARCH_PATH is a trusted constant, not user input.
            with conn.cursor() as c:
                c.execute(f"SET search_path TO {_SEARCH_PATH}")
        return conn
    except Exception:
        # Don't return a half-initialised connection to the pool.
        try:
            _get_pool().putconn(conn, close=True)
        except Exception:
            pass
        raise


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


_columns_cache: dict[str, list[str]] = {}


def _insert_columns(conn, table: str, n: int) -> list[str]:
    """The first `n` writable columns of `table`, in schema order, skipping id
    and owner_id.

    Positional inserts used to rely on owner_id being the trailing column. It
    no longer is: add_column appends after it, and seven tables have gained
    columns that way. Naming the columns keeps a positional caller writing the
    same fields it always did, whatever is appended later."""
    cols = _columns_cache.get(table)
    if cols is None:
        with conn.cursor() as c:
            c.execute("SELECT column_name FROM information_schema.columns "
                      "WHERE table_name = %s AND table_schema = ANY(current_schemas(false)) "
                      "ORDER BY ordinal_position", (table,))
            cols = [r[0] for r in c.fetchall() if r[0] not in ("id", "owner_id")]
        _columns_cache[table] = cols
    if len(cols) < n:
        raise ValueError(f"{table} has {len(cols)} writable columns, got {n} values")
    return cols[:n]


def insert(table, values):
    """Positional insert into an owner-scoped table. Stamps owner_id from the
    current request's owner and returns the generated id. All callers operate
    on owner-scoped tables."""
    owner = require_owner()
    conn = get_conn()
    try:
        c = conn.cursor()
        placeholders = ",".join(["%s"] * len(values))
        cols = ",".join(_insert_columns(conn, table, len(values)))
        c.execute(
            f"INSERT INTO {table} ({cols},owner_id) VALUES ({placeholders},%s) RETURNING id",
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
        # Under autocommit the statement has already settled; commit() and
        # rollback() are no-ops kept so the connection is returned in a known
        # state even if autocommit could not be enabled.
        if commit:
            conn.commit()
        else:
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


_SELECT_HEAD = _re.compile(r"^\s*SELECT\s+(.*?)\sFROM\s(.*)$", _re.S | _re.I)


def json_part(name, sql, params=()):
    """Turn a plain `SELECT cols FROM ...` into a bundle part for
    fetch_bundle(), so a query written for fetch() can be bundled unchanged.

    Only for queries whose column list holds no FROM of its own: the split
    takes the first one. A subquery in the columns would split in the wrong
    place, so that is rejected rather than quietly mis-parsed — write such a
    part by hand.
    """
    m = _SELECT_HEAD.match(sql)
    if not m:
        raise ValueError("not a plain SELECT ... FROM ...")
    cols, rest = m.groups()
    if cols.count("(") != cols.count(")"):
        raise ValueError("column list contains its own FROM; build this part by hand")
    return (name, f"SELECT json_build_array({cols}) FROM {rest}", params)


def fetch_bundle(parts):
    """Run several independent SELECTs in ONE round trip.

    `parts` is a list of (name, sql, params). Each sql must select a single
    column built with json_build_array(...), so the rows come back positional,
    exactly as fetch() would return them — Postgres decides the column order of
    json_agg(t) otherwise, which a positional caller cannot rely on.

    Against a database ~40 ms away, eight independent loads cost eight round
    trips; bundled they cost one. Returns {name: [row, ...]}.
    """
    selects, args = [], []
    for name, sql, ps in parts:
        selects.append(f"(SELECT COALESCE(json_agg(x.v), '[]') FROM ({sql}) x(v)) AS {name}")
        args.extend(ps)
    row = fetch("SELECT " + ", ".join(selects), tuple(args))[0]
    return {name: row[i] for i, (name, _, _) in enumerate(parts)}


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


def get_tenant_gender(tenant_name):
    rows = fetch("SELECT gender FROM tenants WHERE name = ? AND owner_id = ? LIMIT 1",
                 (tenant_name, current_owner()))
    return rows[0][0] if rows else "diverse"
