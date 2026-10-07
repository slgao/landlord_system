"""The same tenancy entered twice.

A contract saved twice is invisible as a mistake afterwards: both rows look
right, and every month they overlap is counted twice in the expected rent.
"""
import pytest
from fastapi import HTTPException

from api.routers import contracts as mod


@pytest.fixture
def existing(monkeypatch):
    """One contract on file: tenant 1, flat 2, starting 2023-04-01."""
    rows = [(32, 1, 2, "2023-04-01")]

    def fake_fetch(sql, params=()):
        q = " ".join(sql.split())
        if "FROM tenants WHERE id=?" in q or "FROM apartments WHERE id=?" in q:
            return [(params[0],)]
        if q.startswith("SELECT id FROM contracts WHERE tenant_id=?"):
            tenant_id, apartment_id, start, _owner = params
            return [(r[0],) for r in rows
                    if (r[1], r[2], r[3]) == (tenant_id, apartment_id, start)]
        raise AssertionError(f"unexpected query: {q}")
    monkeypatch.setattr(mod, "fetch", fake_fetch)
    return rows


def _body(**kw):
    from api.schemas.contract import ContractIn
    return ContractIn(**{"tenant_id": 1, "apartment_id": 2, "rent": 466.12,
                         "start_date": "2023-04-01", **kw})


def test_the_same_tenancy_cannot_be_saved_twice(existing):
    with pytest.raises(HTTPException) as exc:
        mod.create_contract(_body(), owner=1)
    assert exc.value.status_code == 409
    assert "#32" in exc.value.detail          # points at the one already there


def test_a_later_term_for_the_same_flat_is_fine(existing, monkeypatch):
    # A rent change is recorded as a follow-on contract starting the next day.
    monkeypatch.setattr(mod, "_refuse_duplicate", mod._refuse_duplicate)
    mod._refuse_duplicate(1, 2, "2025-04-01", 1)      # does not raise


def test_another_tenant_or_flat_on_the_same_day_is_fine(existing):
    mod._refuse_duplicate(9, 2, "2023-04-01", 1)
    mod._refuse_duplicate(1, 9, "2023-04-01", 1)
