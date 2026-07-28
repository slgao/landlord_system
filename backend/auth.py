"""
Multi-user auth:
- JWT Bearer (Next.js) — `sub` is the user id
- HTTP Basic (email + password) for backward-compatible tooling

Every authenticated request resolves to a user id, which is published to the
request-scoped owner context (db.set_current_owner) so data access is scoped to
that user.

JWT_SECRET — signing key for JWT tokens (random per process if unset)
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.concurrency import run_in_threadpool
from jose import JWTError, jwt

from db import set_current_owner
import users_db

log = logging.getLogger("uvicorn.error")

_JWT_ALGO = "HS256"
_JWT_EXPIRE_HOURS = 24 * 7  # 1 week

# Secrets that must never be used in production: unset (None) or the shipped
# placeholder from docker-compose.yml.
_WEAK_SECRETS = {"", "change-this-in-production-32chars"}

_JWT_SECRET_ENV = (os.environ.get("JWT_SECRET") or "").strip()
# When JWT_SECRET is unset we fall back to a per-process random key. That keeps
# local dev working but silently invalidates every issued token on restart —
# verify_startup_config() warns (dev) or refuses to start (production).
import secrets as _secrets
_JWT_SECRET = _JWT_SECRET_ENV or _secrets.token_hex(32)


def verify_startup_config() -> None:
    """Validate auth secrets at startup. In production (APP_ENV=production) a
    missing/weak JWT_SECRET is fatal; otherwise we only warn."""
    is_prod = os.environ.get("APP_ENV", "development").lower() == "production"
    problems = []
    if _JWT_SECRET_ENV in _WEAK_SECRETS:
        problems.append(
            "JWT_SECRET is unset or the shipped placeholder — set a random 32+ "
            "char value (tokens are otherwise forgeable and reset on restart)."
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


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


def verify_access_token(token: str) -> int:
    """Return the user id encoded in a valid token, else raise 401."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return int(sub)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependency ─────────────────────────────────────────────────────────

_basic = HTTPBasic(auto_error=False)


def _authenticate(request: Request, basic_creds: Optional[HTTPBasicCredentials]) -> int:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        uid = verify_access_token(auth_header[7:])
        user = users_db.get_user_by_id(uid)
        if not user or not user["is_active"]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="User not found or inactive")
        return uid

    if basic_creds:
        user = users_db.get_user_by_email(basic_creds.username)
        if user and user["is_active"] and users_db.verify_password(
                basic_creds.password, user["password_hash"]):
            return user["id"]

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": 'Bearer, Basic realm="Vermio"'},
    )


async def require_auth(
    request: Request,
    basic_creds: Optional[HTTPBasicCredentials] = Depends(_basic),
) -> int:
    """Resolve the authenticated user id, publish it as the request's data owner,
    and return it. Used both as a router-level gate and as an injected dependency
    (`owner: int = Depends(require_auth)`).

    Async on purpose: set_current_owner() must run in the request's event-loop
    context so run_in_threadpool copies the owner into the (sync) endpoint's
    thread — a ContextVar set from a *sync* dependency would not propagate.
    """
    uid = await run_in_threadpool(_authenticate, request, basic_creds)
    set_current_owner(uid)
    return uid
