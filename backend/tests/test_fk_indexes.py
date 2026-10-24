"""The foreign-key index guard.

An unindexed foreign key is the one performance fault that cannot be seen on a
developer's database: with a hundred rows a sequential scan is the fastest plan
there is, so the page is quick until other people's data arrives. The schema
check at boot is what notices, so it is worth a test of its own.
"""
import importlib.util
import pathlib

import db


def _migration(name):
    """Load a migration by path — alembic/versions is a script directory, not
    an importable package."""
    path = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FK_INDEXES = _migration("c3d4e5f6a0b1_index_foreign_keys.py").FK_INDEXES


def test_nothing_to_say_when_every_key_is_indexed():
    assert db.describe_unindexed_fks([]) is None


def test_the_warning_names_the_columns():
    msg = db.describe_unindexed_fks([
        ("payments", "contract_id", "contracts"),
        ("apartments", "property_id", "properties"),
    ])
    assert "2 foreign key(s)" in msg
    assert "payments.contract_id" in msg
    assert "apartments.property_id" in msg


def test_the_query_asks_for_the_leading_column_only():
    # A composite index on (owner_id, contract_id) does not help a join on
    # contract_id, so the check must look at indkey[0] and at conkey's first
    # column — not at "is this column in any index somewhere".
    assert "indkey[0]" in db._UNINDEXED_FKS_SQL
    assert "k.ord = 1" in db._UNINDEXED_FKS_SQL


def test_rows_come_back_as_plain_strings():
    # psycopg2 hands regclass back as str already, but the formatter is also
    # fed from tests and from a log line, so the shape is pinned here.
    rows = [("payments", "contract_id", "contracts")]
    assert db.describe_unindexed_fks(rows).endswith("payments.contract_id")


def test_the_migration_covers_the_hot_join():
    # payments.contract_id is the column the arrears query joins on; without
    # it the query reads every landlord's payments. If this ever disappears
    # from the migration, the 19× regression comes back silently.
    assert ("ix_payments_contract_id", "payments", "contract_id") in FK_INDEXES


def test_migration_index_names_are_unique_and_conventional():
    names = [n for n, _t, _c in FK_INDEXES]
    assert len(names) == len(set(names))
    for name, table, column in FK_INDEXES:
        assert name == f"ix_{table}_{column}"
