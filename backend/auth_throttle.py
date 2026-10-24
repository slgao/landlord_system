"""How many times you may guess, and how long a wrong guess takes.

Two measurements on this API before any of this existed:

    ten wrong passwords in a row     → ten 401s, no delay, no limit
    wrong password, account exists    → 270 ms
    wrong password, no such account   →   2 ms

The second pair is the more interesting one. bcrypt is deliberately slow, so a
login that verifies a hash takes a quarter of a second and one that cannot find
the user returns immediately — which answers "does this person have an account
here?" for any address you care to try, 150× faster than it answers anything
else. For a landlord's tenants' data, the list of who has an account is itself
worth not giving away.

So: every attempt costs a bcrypt verify whether the account exists or not, and
attempts are counted — per account and per source address, because limiting
only one of them leaves either a single account open to a botnet or a single
address free to work through a list of accounts.

In-process counters, not Redis: this is one uvicorn process per deployment, and
a counter that forgets everything on restart is still the difference between
thousands of guesses an hour and twenty.
"""
from __future__ import annotations

import os
import threading
import time

# A dummy hash to verify against when the account does not exist. bcrypt of a
# value nobody can supply; it exists only to burn the same ~250 ms the real
# path burns. Generated at import, so it is never a value an attacker knows.
_DECOY_HASH: str | None = None
_decoy_lock = threading.Lock()


def decoy_hash() -> str:
    global _DECOY_HASH
    if _DECOY_HASH is None:
        with _decoy_lock:
            if _DECOY_HASH is None:
                import secrets
                import users_db
                _DECOY_HASH = users_db.hash_password(secrets.token_hex(16))
    return _DECOY_HASH


# Failures allowed inside the window, and how long the window is.
# Deliberately loose enough that a person mistyping a password a few times is
# never locked out, and tight enough that guessing is pointless: 20 attempts
# per 15 minutes is 80 a day against one account.
MAX_FAILURES = int(os.environ.get("AUTH_MAX_FAILURES", "20"))
# The address gets a larger budget than the account, because an address is not
# a person: a household, an office or a phone network shares one, and the
# account budget would otherwise let one colleague's fumbling lock out
# everyone behind the same NAT. It still has to be bounded, or working through
# a list of accounts from one machine costs nothing.
MAX_FAILURES_IP = int(os.environ.get("AUTH_MAX_FAILURES_IP", str(MAX_FAILURES * 5)))
WINDOW_S = float(os.environ.get("AUTH_FAILURE_WINDOW", str(15 * 60)))


def _limit_for(key: str) -> int:
    return MAX_FAILURES_IP if key.startswith("ip:") else MAX_FAILURES
# A bound on the table itself, so a flood of distinct addresses cannot make the
# counters the memory leak. When it is reached the expired entries go first,
# and only if that frees nothing does the table start over.
MAX_KEYS = 4096

_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def _prune(now: float) -> None:
    for key, stamps in list(_failures.items()):
        fresh = [t for t in stamps if t > now - WINDOW_S]
        if fresh:
            _failures[key] = fresh
        else:
            del _failures[key]


def too_many_attempts(keys) -> bool:
    """Has any of these keys used up its budget? Checked before the password is
    verified, so a locked-out key costs nothing to refuse."""
    if MAX_FAILURES <= 0:
        return False
    now = time.monotonic()
    with _lock:
        for key in keys:
            stamps = _failures.get(key)
            if stamps and sum(1 for t in stamps if t > now - WINDOW_S) >= _limit_for(key):
                return True
    return False


def record_attempt(keys) -> None:
    """Spend one attempt against each key. Called for a failed login, and for
    a registration whether it succeeded or not — the budget there is on
    creating accounts, not on getting them wrong."""
    now = time.monotonic()
    with _lock:
        if len(_failures) >= MAX_KEYS:
            _prune(now)
            if len(_failures) >= MAX_KEYS:
                _failures.clear()
        for key in keys:
            _failures.setdefault(key, []).append(now)


def clear(keys) -> None:
    """A correct password forgives the earlier typos."""
    with _lock:
        for key in keys:
            _failures.pop(key, None)


def reset() -> None:
    """For tests."""
    with _lock:
        _failures.clear()


def client_ip(request) -> str:
    """The caller's address, trusting X-Forwarded-For only when told to.

    Behind a reverse proxy every request arrives from the proxy, so without
    the header the per-address limit would be one bucket for the whole
    internet. But the header is caller-supplied: trusting it when there is no
    proxy lets anyone mint a fresh address per attempt and skip the limit
    entirely. TRUST_PROXY_HEADERS=1 says a proxy is in front.
    """
    if os.environ.get("TRUST_PROXY_HEADERS", "").strip().lower() in ("1", "true", "yes"):
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return getattr(getattr(request, "client", None), "host", None) or "unknown"


def keys_for(email: str, request) -> list[str]:
    """What this attempt counts against: the account and the address."""
    return [f"user:{(email or '').strip().lower()}", f"ip:{client_ip(request)}"]
