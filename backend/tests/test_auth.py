"""Tests for JWT round-tripping and the production-config startup guard."""
import bcrypt
import pytest
from fastapi import HTTPException

import auth


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_jwt_roundtrip():
    token = auth.create_access_token("alice")
    assert auth.verify_access_token(token) == "alice"


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
