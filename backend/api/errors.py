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
