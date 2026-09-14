"""Tests for JWT round-tripping and the production-config startup guard."""
import bcrypt
import pytest
from fastapi import HTTPException

import auth


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_jwt_roundtrip():
    # Tokens now carry the integer user id as the subject (multi-user auth).
    token = auth.create_access_token(42)
    assert auth.verify_access_token(token) == 42


def test_verify_rejects_garbage_token():
    with pytest.raises(HTTPException) as exc:
        auth.verify_access_token("not-a-real-token")
    assert exc.value.status_code == 401


# ── verify_startup_config ─────────────────────────────────────────────────────

def test_dev_config_only_warns(monkeypatch):
    # conftest cleared JWT_SECRET/APP_PASSWORD_HASH, so config is insecure.
    monkeypatch.delenv("APP_ENV", raising=False)
    # Should not raise in development, even with weak/missing secrets.
    auth.verify_startup_config()


def test_production_rejects_weak_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "_JWT_SECRET_ENV", "")   # unset / placeholder
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    with pytest.raises(RuntimeError) as exc:
        auth.verify_startup_config()
    assert "JWT_SECRET" in str(exc.value)


def test_production_rejects_placeholder_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "_JWT_SECRET_ENV", "change-this-in-production-32chars")
    monkeypatch.setenv("APP_PASSWORD_HASH",
                       bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode())
    with pytest.raises(RuntimeError):
        auth.verify_startup_config()


def test_production_accepts_strong_config(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "_JWT_SECRET_ENV", "x" * 40)
    monkeypatch.setenv("APP_PASSWORD_HASH",
                       bcrypt.hashpw(b"pw", bcrypt.gensalt()).decode())
    # Strong secret + password hash set → no exception.
    auth.verify_startup_config()


# ── the auth lookup cache ─────────────────────────────────────────────────────

ACTIVE = {"id": 7, "email": "a@b.de", "is_active": True}


@pytest.fixture(autouse=True)
def _clear_auth_cache():
    """Each test starts from an empty cache and leaves one behind."""
    auth.invalidate_user()
    yield
    auth.invalidate_user()


class _Counter:
    """Stands in for users_db.get_user_by_id and counts the round trips."""

    def __init__(self, row):
        self.row = row
        self.calls = 0

    def __call__(self, user_id):
        self.calls += 1
        return self.row


def test_second_lookup_does_not_hit_the_database(monkeypatch):
    spy = _Counter(ACTIVE)
    monkeypatch.setattr(auth.users_db, "get_user_by_id", spy)

    assert auth.active_user(7) == ACTIVE
    assert auth.active_user(7) == ACTIVE
    assert auth.active_user(7) == ACTIVE
    assert spy.calls == 1


def test_expired_entry_is_looked_up_again(monkeypatch):
    spy = _Counter(ACTIVE)
    monkeypatch.setattr(auth.users_db, "get_user_by_id", spy)
    monkeypatch.setattr(auth, "_AUTH_CACHE_TTL_S", 30.0)

    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])

    auth.active_user(7)
    clock[0] += 29.0          # still inside the window
    auth.active_user(7)
    assert spy.calls == 1

    clock[0] += 2.0           # past it
    auth.active_user(7)
    assert spy.calls == 2


def test_inactive_and_missing_users_are_cached_as_unusable(monkeypatch):
    """A rejected token must not cost a query per request either."""
    for row in (None, {"id": 7, "is_active": False}):
        auth.invalidate_user()
        spy = _Counter(row)
        monkeypatch.setattr(auth.users_db, "get_user_by_id", spy)

        assert auth.active_user(7) is None
        assert auth.active_user(7) is None
        assert spy.calls == 1


def test_invalidate_user_forces_a_fresh_lookup(monkeypatch):
    spy = _Counter(ACTIVE)
    monkeypatch.setattr(auth.users_db, "get_user_by_id", spy)

    auth.active_user(7)
    auth.invalidate_user(7)
    auth.active_user(7)
    assert spy.calls == 2

    auth.active_user(7)
    auth.invalidate_user()        # no argument clears everything
    auth.active_user(7)
    assert spy.calls == 3


def test_ttl_zero_disables_the_cache(monkeypatch):
    spy = _Counter(ACTIVE)
    monkeypatch.setattr(auth.users_db, "get_user_by_id", spy)
    monkeypatch.setattr(auth, "_AUTH_CACHE_TTL_S", 0.0)

    auth.active_user(7)
    auth.active_user(7)
    assert spy.calls == 2


def test_cache_does_not_grow_without_bound(monkeypatch):
    spy = _Counter(ACTIVE)
    monkeypatch.setattr(auth.users_db, "get_user_by_id", spy)
    monkeypatch.setattr(auth, "_AUTH_CACHE_MAX", 8)

    for uid in range(40):
        auth.active_user(uid)
    assert len(auth._user_cache) <= 8


def test_authenticate_rejects_a_token_whose_user_is_gone(monkeypatch):
    """The cache must not turn a 401 into a pass."""
    monkeypatch.setattr(auth.users_db, "get_user_by_id", lambda uid: None)

    class _Req:
        headers = {"Authorization": f"Bearer {auth.create_access_token(7)}"}

    with pytest.raises(HTTPException) as exc:
        auth._authenticate(_Req(), None)
    assert exc.value.status_code == 401


def test_authenticate_accepts_an_active_user(monkeypatch):
    monkeypatch.setattr(auth.users_db, "get_user_by_id", lambda uid: ACTIVE)

    class _Req:
        headers = {"Authorization": f"Bearer {auth.create_access_token(7)}"}

    assert auth._authenticate(_Req(), None) == 7
