"""
Lightweight password gate for Streamlit and FastAPI.

Both layers verify a bcrypt hash stored in the APP_PASSWORD_HASH env var.
Generate one with:
    python -c 'import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())'

If APP_PASSWORD_HASH is not set, both gates open transparently — useful for
local single-user development. Set the variable before exposing the app
beyond localhost.
"""
import os
import secrets

import bcrypt
import streamlit as st
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_HASH_ENV = "APP_PASSWORD_HASH"
_USERNAME = os.environ.get("APP_USERNAME", "admin")


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


# ── Streamlit ────────────────────────────────────────────────────────────────

def streamlit_gate() -> None:
    """Block page rendering until the user enters the correct password.

    Call once at the top of app.py, before any page logic. No-op when
    APP_PASSWORD_HASH is unset.
    """
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

_basic = HTTPBasic()


def require_auth(creds: HTTPBasicCredentials = Depends(_basic)) -> str:
    """FastAPI dependency. Returns the authenticated username, or 401s.

    No-op (returns 'anonymous') when APP_PASSWORD_HASH is unset.
    """
    if _password_hash() is None:
        return "anonymous"

    user_ok = secrets.compare_digest(creds.username, _USERNAME)
    pw_ok = _verify(creds.password)
    if not (user_ok and pw_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username
