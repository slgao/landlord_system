"""get_conn waits for a free pooled connection instead of failing the request
the instant the pool is fully checked out."""
import pytest
from psycopg2 import pool as pg_pool

import db


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.autocommit = False
    def cursor(self):
        conn = self
        class _C:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def execute(s, q): conn.executed.append(q)
        return _C()


class _FlakyPool:
    """Raises PoolError `fail_times` times, then hands out a connection."""
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0
    def getconn(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise pg_pool.PoolError("connection pool exhausted")
        return _FakeConn()
    def putconn(self, conn, close=False):
        pass


def test_get_conn_waits_then_succeeds(monkeypatch):
    fake = _FlakyPool(fail_times=3)
    monkeypatch.setattr(db, "_get_pool", lambda: fake)
    monkeypatch.setattr(db, "_POOL_WAIT_S", 2.0)
    monkeypatch.setattr(db, "_needs_search_path", True)   # force the slow path
    conn = db.get_conn()
    assert fake.calls == 4
    assert conn.executed and conn.executed[0].startswith("SET search_path")
    # Autocommit is what removes the BEGIN/COMMIT round trips per statement.
    assert conn.autocommit is True


def test_get_conn_gives_up_after_the_deadline(monkeypatch):
    fake = _FlakyPool(fail_times=10_000)
    monkeypatch.setattr(db, "_get_pool", lambda: fake)
    monkeypatch.setattr(db, "_POOL_WAIT_S", 0.2)
    with pytest.raises(pg_pool.PoolError):
        db.get_conn()
    assert 2 <= fake.calls < 50


def test_search_path_is_set_only_when_the_default_does_not_resolve(monkeypatch):
    """The SET is a whole extra round trip on every query, so it is skipped
    when the role's own search_path already finds the tables."""
    fake = _FlakyPool(fail_times=0)
    monkeypatch.setattr(db, "_get_pool", lambda: fake)

    monkeypatch.setattr(db, "_needs_search_path", False)
    assert db.get_conn().executed == []

    monkeypatch.setattr(db, "_needs_search_path", True)
    assert db.get_conn().executed[0].startswith("SET search_path")


def test_the_probe_runs_once_and_decides(monkeypatch):
    fake = _FlakyPool(fail_times=0)
    monkeypatch.setattr(db, "_get_pool", lambda: fake)
    monkeypatch.setattr(db, "_needs_search_path", None)
    probes = []

    def probe(conn):
        probes.append(conn)
        return False                      # default path resolves; no SET needed
    monkeypatch.setattr(db, "_probe_search_path", probe)

    for _ in range(3):
        assert db.get_conn().executed == []
    assert len(probes) == 1               # asked the database once, not per query


def test_an_unusable_probe_keeps_the_safe_behaviour(monkeypatch):
    """If the check itself fails we must not conclude the path is fine."""
    class _Boom:
        autocommit = False
        def cursor(self): raise RuntimeError("no cursor")
    assert db._probe_search_path(_Boom()) is True
