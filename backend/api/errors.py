"""How an unexpected exception reaches the client.

Two rules pull against each other. The browser needs *something* — a crash
rendered outside the CORS middleware arrives as an opaque "NetworkError" with
the cause invisible, which is why these paths exist at all. But the exception
text itself is not ours to hand out: a psycopg2 failure carries the database
host and user, and the routes below include unauthenticated ones, so a
database outage would have answered an anonymous login attempt with the
infrastructure behind it.

So the client gets a stable, meaningless id and the log gets everything.
"""
import logging
import traceback
import uuid

log = logging.getLogger("uvicorn.error")


def log_and_reference(exc: Exception, where: str) -> str:
    """Record the traceback against a short id and return the id, which is the
    only part of it the caller may show a user."""
    ref = uuid.uuid4().hex[:8]
    log.error("Unhandled error [%s] on %s\n%s", ref, where,
              "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return ref


def client_detail(ref: str) -> str:
    return (f"Something went wrong on the server (error {ref}). "
            f"The cause is in the API log under that id.")


# Database refusals that are the *client's* fault, and what to say about each.
# A value the schema will not take is a 422, not a crash: `living_sqm:
# 999999999999` in a NUMERIC(10,2) column, or a 500-character city in a
# VARCHAR, used to come back as "Something went wrong on the server", which
# tells the person filling in the form nothing they can act on.
#
# Keyed by psycopg2's SQLSTATE so a new psycopg2 release cannot rename the
# exception class out from under this. The message never repeats the database's
# own text: that carries the host, the user and the schema.
_DB_CLIENT_ERRORS = {
    "22003": (422, "A number is too large for the field it goes in."),
    "22001": (422, "A value is longer than the field it goes in."),
    "22007": (422, "A date is not in a form the database accepts."),
    "22P02": (422, "A value is not of the type the field expects."),
    "23502": (422, "A required value is missing."),
    "23514": (422, "A value is outside the range this field allows."),
    "23505": (409, "That record already exists."),
    "23503": (409, "That record refers to something that does not exist, "
                   "or is still referred to by something else."),
}


_NON_FINITE_DETAIL = ("A number is not finite. NaN and infinity cannot be stored "
                      "or reported on, so they are refused.")


def db_error_response(exc: Exception):
    """(status, detail) when a database error is really a bad request, else None.

    Everything not listed stays an unhandled 500 with a reference id: an
    outage, a syntax error or a permission problem is ours, not the caller's,
    and saying "422" about it would hide a real fault.
    """
    from db import NonFiniteNumber
    if isinstance(exc, NonFiniteNumber):
        # Refused before the statement ran: `{"amount": "NaN"}` is a string,
        # so the body check at the door does not see a number at all.
        return 422, _NON_FINITE_DETAIL

    code = getattr(getattr(exc, "pgcode", None), "strip", lambda: None)() or getattr(
        exc, "pgcode", None)
    hit = _DB_CLIENT_ERRORS.get(code)
    if not hit:
        return None
    status, detail = hit
    log.info("database refused a request (SQLSTATE %s): %s", code, detail)
    return status, detail
