"""Shared test setup.

`db.py` reads DATABASE_URL at import time and `logic.py` imports `db`, so a
value must exist before any test module is imported. The connection pool is
created lazily, so a dummy URL is fine for the pure-function tests here — none
of them actually open a connection.

We also clear the auth secrets so `verify_startup_config` sees a known
(insecure) baseline regardless of the developer's shell environment.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.pop("JWT_SECRET", None)
os.environ.pop("APP_PASSWORD_HASH", None)
os.environ.pop("APP_ENV", None)
