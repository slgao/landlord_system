"""The whole portfolio in one file.

The question a self-hosted tool has to answer before anyone commits ten years
of records to it: can I get them out again. §147 AO wants those records
readable for ten years, which a running container does not promise.
"""
import json

import pytest

from api.routers import export


def test_every_table_is_scoped_to_the_caller():
    # One missing WHERE here would hand a landlord someone else's portfolio,
    # in a single file, by design.
    import inspect
    src = inspect.getsource(export.collect)
    assert "WHERE owner_id = ?" in src
    assert src.count("fetch(") == 1          # one query shape, not many to check


def test_the_settings_table_is_not_in_the_export():
    # config holds the SMTP password, encrypted with a key that is not in the
    # file. Exporting it would either leak a secret or write an unreadable blob.
    assert "config" not in export.TABLES


def test_the_rent_periods_travel_with_the_contracts():
    # A contract without its prices would restore as a tenancy that earns
    # nothing — the export has to carry what the reports read.
    assert "contract_rents" in export.TABLES
    assert "contracts" in export.TABLES


def test_pdfs_are_flagged_rather_than_embedded():
    for table in ("expenses", "nk_settlements"):
        assert "has_pdf" in export.TABLES[table]
        assert "pdf," not in export.TABLES[table]


def test_money_survives_as_text_not_as_a_float():
    from decimal import Decimal
    # 1050.25 as a JSON number is a float, and this file is meant to still be
    # exact in ten years.
    assert export._json_default(Decimal("1050.25")) == "1050.25"
    assert json.dumps({"a": Decimal("0.1")}, default=export._json_default) == '{"a": "0.1"}'


def test_bytes_never_reach_the_file():
    assert export._json_default(b"%PDF-1.4") is None
    assert export._json_default(memoryview(b"x")) is None


def test_a_missing_table_does_not_fail_the_whole_export(monkeypatch):
    calls = {"n": 0}

    def flaky(sql, params=()):
        calls["n"] += 1
        if "FROM gas_meters" in sql:
            raise RuntimeError('relation "gas_meters" does not exist')
        return []

    monkeypatch.setattr(export, "fetch", flaky)
    data = export.collect(owner=1)
    assert "gas_meters" not in data            # absent, and visibly so
    assert "properties" in data
    assert calls["n"] == len(export.TABLES)


def test_rows_come_back_keyed_by_column(monkeypatch):
    def one_row(sql, params=()):
        if "FROM tenants" in sql:
            return [(1, "Anna Schmidt", "frau", "anna@example.de", "0170")]
        return []
    monkeypatch.setattr(export, "fetch", one_row)
    data = export.collect(owner=1)
    assert data["tenants"] == [{"id": 1, "name": "Anna Schmidt", "gender": "frau",
                                "email": "anna@example.de", "phone": "0170"}]


def test_a_computed_column_keeps_its_alias(monkeypatch):
    def rows(sql, params=()):
        if "FROM nk_settlements" in sql:
            return [(7, 1, "2025-01-01", "2025-12-31", 180.0, "2026-03-01", None, True)]
        return []
    monkeypatch.setattr(export, "fetch", rows)
    row = export.collect(owner=1)["nk_settlements"][0]
    assert row["has_pdf"] is True
    assert row["id"] == 7
