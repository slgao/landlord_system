"""
Auth module supporting:
- Streamlit password gate
- FastAPI HTTP Basic (backward compat)
- FastAPI JWT Bearer (Next.js)

APP_PASSWORD_HASH  — bcrypt hash of the app password (open if unset)
APP_USERNAME       — login username (default: admin)
JWT_SECRET         — signing key for JWT tokens (random per process if unset)

Generate a hash:
    python -c 'import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())'
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from jose import JWTError, jwt

_HASH_ENV = "APP_PASSWORD_HASH"
_USERNAME = os.environ.get("APP_USERNAME", "admin")
_JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
_JWT_ALGO = "HS256"
_JWT_EXPIRE_HOURS = 24 * 7  # 1 week


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


# ── Streamlit ────────────────────────────────────────────────────────────────

def streamlit_gate() -> None:
    try:
        import streamlit as st
    except ImportError:
        return

    if _password_hash() is None:
        return
    if st.session_state.get("_authed"):
        return

    st.title("🔒 Hausverwaltung")
    pw = st.text_input("Password", type="password", key="_login_pw")
    if st.button("Sign in", key="_login_btn"):
        if _verify(pw):
            st.session_state["_authed"] = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()


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
