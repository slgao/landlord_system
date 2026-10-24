"""Guessing limits, and the timing oracle they sit beside.

Measured before any of this: ten wrong passwords in a row were answered with
ten immediate 401s, and a wrong password took 270 ms for an address that has an
account against 2 ms for one that does not — which is a yes/no answer to "does
this person have an account here", for any address, 150× faster than the API
answers anything else.
"""
import time

import pytest

import auth_throttle as t


@pytest.fixture(autouse=True)
def _clean():
    t.reset()
    yield
    t.reset()


class _Req:
    def __init__(self, host="203.0.113.7", headers=None):
        self.client = type("C", (), {"host": host})()
        self.headers = headers or {}


# ── Counting ─────────────────────────────────────────────────────────────────

def test_a_few_typos_are_not_a_lockout():
    keys = t.keys_for("a@b.de", _Req())
    for _ in range(t.MAX_FAILURES - 1):
        t.record_attempt(keys)
    assert not t.too_many_attempts(keys)


def test_the_budget_runs_out():
    keys = t.keys_for("a@b.de", _Req())
    for _ in range(t.MAX_FAILURES):
        t.record_attempt(keys)
    assert t.too_many_attempts(keys)


def test_getting_in_forgives_the_earlier_typos():
    keys = t.keys_for("a@b.de", _Req())
    for _ in range(t.MAX_FAILURES):
        t.record_attempt(keys)
    t.clear(keys)
    assert not t.too_many_attempts(keys)


def test_the_window_expires(monkeypatch):
    keys = t.keys_for("a@b.de", _Req())
    base = time.monotonic()
    monkeypatch.setattr(t.time, "monotonic", lambda: base)
    for _ in range(t.MAX_FAILURES):
        t.record_attempt(keys)
    assert t.too_many_attempts(keys)
    monkeypatch.setattr(t.time, "monotonic", lambda: base + t.WINDOW_S + 1)
    assert not t.too_many_attempts(keys)


# ── Both keys, because either alone has a hole ───────────────────────────────

def test_one_address_cannot_work_through_a_list_of_accounts():
    # Same caller, a different account each time: the per-account counter
    # never fills, so the per-address one has to.
    req = _Req("198.51.100.4")
    for i in range(t.MAX_FAILURES_IP):
        t.record_attempt(t.keys_for(f"victim{i}@example.com", req))
    assert t.too_many_attempts(t.keys_for("someone-new@example.com", req))


def test_an_address_is_not_a_person_so_it_gets_a_larger_budget():
    # A household or an office shares one address. Spending the per-account
    # budget from it must not lock out the colleague at the next desk.
    assert t.MAX_FAILURES_IP > t.MAX_FAILURES
    req = _Req("198.51.100.9")
    for _ in range(t.MAX_FAILURES):
        t.record_attempt(t.keys_for("one-colleague@example.com", req))
    assert t.too_many_attempts(t.keys_for("one-colleague@example.com", req))
    assert not t.too_many_attempts(t.keys_for("another-colleague@example.com", req))


def test_a_botnet_cannot_grind_one_account():
    # A different address each time: the per-address counter never fills, so
    # the per-account one has to.
    for i in range(t.MAX_FAILURES):
        t.record_attempt(t.keys_for("victim@example.com", _Req(f"10.0.0.{i}")))
    assert t.too_many_attempts(t.keys_for("victim@example.com", _Req("10.9.9.9")))


def test_an_unrelated_account_from_a_fresh_address_is_unaffected():
    for _ in range(t.MAX_FAILURES):
        t.record_attempt(t.keys_for("victim@example.com", _Req("10.0.0.1")))
    assert not t.too_many_attempts(t.keys_for("someone@else.de", _Req("10.0.0.2")))


def test_the_account_key_ignores_case_and_padding():
    assert t.keys_for("  A@B.DE ", _Req())[0] == t.keys_for("a@b.de", _Req())[0]


# ── The forwarded address is only trusted when a proxy is declared ───────────

def test_a_forwarded_header_is_ignored_by_default(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    req = _Req("172.16.0.1", {"X-Forwarded-For": "1.2.3.4"})
    assert t.client_ip(req) == "172.16.0.1"


def test_a_forwarded_header_is_used_when_a_proxy_is_declared(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    req = _Req("172.16.0.1", {"X-Forwarded-For": "1.2.3.4, 172.16.0.1"})
    assert t.client_ip(req) == "1.2.3.4"


def test_a_caller_with_no_address_still_gets_a_bucket():
    class _Bare:
        client = None
        headers = {}
    assert t.client_ip(_Bare()) == "unknown"


# ── The table cannot grow without bound ──────────────────────────────────────

def test_a_flood_of_addresses_does_not_grow_the_table_forever():
    for i in range(t.MAX_KEYS + 50):
        t.record_attempt([f"ip:10.1.{i // 256}.{i % 256}"])
    assert len(t._failures) <= t.MAX_KEYS


# ── The decoy hash ───────────────────────────────────────────────────────────

def test_the_decoy_is_a_real_bcrypt_hash_no_password_matches():
    import users_db
    h = t.decoy_hash()
    assert h.startswith("$2")                      # a bcrypt hash, so verifying costs
    assert t.decoy_hash() is h                     # computed once
    for guess in ("", "password", "correct-horse-battery", h):
        assert users_db.verify_password(guess, h) is False


def test_verifying_against_the_decoy_costs_about_what_a_real_one_costs():
    # The point of the decoy: an unknown account must not be answered faster
    # than a known one. Both run one bcrypt verify; this checks the decoy is
    # not a cheap stub that would give the difference away again.
    import users_db
    real = users_db.hash_password("correct-horse-battery")

    def ms(h):
        t0 = time.perf_counter()
        users_db.verify_password("wrong-password", h)
        return (time.perf_counter() - t0) * 1000

    decoy_ms, real_ms = ms(t.decoy_hash()), ms(real)
    assert decoy_ms > 1                            # not an early return
    assert 0.2 < decoy_ms / real_ms < 5            # the same order of work
