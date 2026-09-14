"""An unexpected exception must reach the browser without carrying the server's
internals with it: these routes include unauthenticated ones, and a psycopg2
failure names the database host and user."""
import logging

import pytest

from api.errors import client_detail, log_and_reference


def test_reference_is_short_stable_and_says_nothing():
    exc = RuntimeError("could not connect to db.internal:5432 as neondb_owner")
    ref = log_and_reference(exc, "POST /api/auth/token")
    assert len(ref) == 8 and ref.isalnum()
    detail = client_detail(ref)
    assert ref in detail
    for secret in ("db.internal", "5432", "neondb_owner", "RuntimeError"):
        assert secret not in detail


def test_the_traceback_still_reaches_the_log(caplog):
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        ref = log_and_reference(ValueError("boom at db.internal"), "GET /x")
    logged = caplog.text
    assert ref in logged and "boom at db.internal" in logged and "ValueError" in logged


def test_two_failures_get_different_references():
    a = log_and_reference(ValueError("a"), "GET /x")
    b = log_and_reference(ValueError("a"), "GET /x")
    assert a != b


def test_surface_errors_passes_a_deliberate_httpexception_through():
    # A message the endpoint wrote itself is meant for the user and survives;
    # only unexpected exceptions are reduced to a reference.
    from fastapi import HTTPException
    from api.routers.reports import _surface_errors

    @_surface_errors
    def deliberate():
        raise HTTPException(status_code=404, detail="No expenses recorded for 2031")

    with pytest.raises(HTTPException) as exc:
        deliberate()
    assert exc.value.status_code == 404
    assert exc.value.detail == "No expenses recorded for 2031"


def test_surface_errors_reduces_an_unexpected_one():
    from fastapi import HTTPException
    from api.routers.reports import _surface_errors

    @_surface_errors
    def crashes():
        raise KeyError("host=db.internal user=neondb_owner")

    with pytest.raises(HTTPException) as exc:
        crashes()
    assert exc.value.status_code == 500
    assert "db.internal" not in exc.value.detail
    assert "neondb_owner" not in exc.value.detail
    assert "error " in exc.value.detail
