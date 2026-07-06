"""
Auth module supporting:
- FastAPI HTTP Basic (backward compat)
- FastAPI JWT Bearer (Next.js)

APP_PASSWORD_HASH  — bcrypt hash of the app password (open if unset)
APP_USERNAME       — login username (default: admin)
JWT_SECRET         — signing key for JWT tokens (random per process if unset)

Generate a hash:
    python -c 'import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())'
"""
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jose import JWTError, jwt

log = logging.getLogger("uvicorn.error")

_HASH_ENV = "APP_PASSWORD_HASH"
_USERNAME = os.environ.get("APP_USERNAME", "admin")
_JWT_ALGO = "HS256"
_JWT_EXPIRE_HOURS = 24 * 7  # 1 week

# Secrets that must never be used in production: unset (None) or the shipped
# placeholder from docker-compose.yml.
_WEAK_SECRETS = {"", "change-this-in-production-32chars"}

_JWT_SECRET_ENV = (os.environ.get("JWT_SECRET") or "").strip()
# When JWT_SECRET is unset we fall back to a per-process random key. That keeps
# local dev working but silently invalidates every issued token on restart —
# verify_startup_config() warns (dev) or refuses to start (production).
_JWT_SECRET = _JWT_SECRET_ENV or secrets.token_hex(32)


def verify_startup_config() -> None:
    """Validate auth secrets at startup. In production (APP_ENV=production) a
    missing/weak JWT_SECRET or an unset APP_PASSWORD_HASH is fatal; otherwise
    we only warn so local dev stays frictionless."""
    is_prod = os.environ.get("APP_ENV", "development").lower() == "production"
    problems = []
    if _JWT_SECRET_ENV in _WEAK_SECRETS:
        problems.append(
            "JWT_SECRET is unset or the shipped placeholder — set a random 32+ "
            "char value (tokens are otherwise forgeable and reset on restart)."
        )
    if _password_hash() is None:
        problems.append(
            "APP_PASSWORD_HASH is unset — the API is open to anyone who can reach it."
        )
    if not problems:
        return
    if is_prod:
        raise RuntimeError(
            "Refusing to start in production with insecure auth config:\n  - "
            + "\n  - ".join(problems)
        )
    for p in problems:
        log.warning("auth: %s", p)


def _password_hash() -> str | None:
    h = os.environ.get(_HASH_ENV, "").strip()
    return h or None


def _verify(password: str) -> bool:
    h = _password_hash()
    if not h:
        return True
    try:
        return bcrypt.checkpw(password.encode("utf-8"), h.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


def verify_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return sub
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI ──────────────────────────────────────────────────────────────────

_basic = HTTPBasic(auto_error=False)


def require_auth(
    request: Request,
    basic_creds: Optional[HTTPBasicCredentials] = Depends(_basic),
) -> str:
    """Accept JWT Bearer token or HTTP Basic. Open when APP_PASSWORD_HASH is unset."""
    if _password_hash() is None:
        return "anonymous"

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return verify_access_token(auth_header[7:])

    if basic_creds:
        user_ok = secrets.compare_digest(basic_creds.username, _USERNAME)
        pw_ok = _verify(basic_creds.password)
        if user_ok and pw_ok:
            return basic_creds.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": 'Bearer, Basic realm="Hausverwaltung"'},
    )
