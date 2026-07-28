"""User accounts for multi-user auth. Users are the owners; they have no
owner_id themselves and are not subject to per-tenant scoping."""
import bcrypt
from db import fetch, execute, execute_returning


def _row(r) -> dict:
    return {"id": r[0], "email": r[1], "password_hash": r[2],
            "display_name": r[3], "is_active": bool(r[4])}


def get_user_by_email(email: str) -> dict | None:
    rows = fetch(
        "SELECT id, email, password_hash, display_name, is_active "
        "FROM users WHERE lower(email) = lower(?)", (email,))
    return _row(rows[0]) if rows else None


def get_user_by_id(user_id: int) -> dict | None:
    rows = fetch(
        "SELECT id, email, password_hash, display_name, is_active "
        "FROM users WHERE id = ?", (user_id,))
    return _row(rows[0]) if rows else None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_user(email: str, password: str, display_name: str | None = None) -> int:
    return execute_returning(
        "INSERT INTO users (email, password_hash, display_name) VALUES (?,?,?) RETURNING id",
        (email.strip(), hash_password(password), display_name),
    )[0][0]


def set_password(user_id: int, password: str) -> None:
    execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id))
