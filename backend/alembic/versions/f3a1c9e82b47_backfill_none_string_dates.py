"""backfill 'None' string to NULL in all TEXT date columns

Revision ID: f3a1c9e82b47
Revises: e7a3b2f9d104
Create Date: 2026-05-01

Legacy code called str(None) which wrote the literal string 'None' into TEXT
date columns instead of SQL NULL.  This migration replaces those rows with
proper NULLs so date comparisons and IS NULL checks work correctly.
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'f3a1c9e82b47'
down_revision: Union[str, Sequence[str], None] = 'd1f8c63a7259'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NONE_COLUMNS = [
    ("contracts",         "end_date"),
    ("contracts",         "kaution_paid_date"),
    ("contracts",         "kaution_returned_date"),
    ("flat_costs",        "valid_from"),
    ("flat_costs",        "valid_to"),
    ("kaution_deductions","date"),
    ("payments",          "payment_date"),
    ("reminders",         "sent_date"),
]


def upgrade() -> None:
    for table, col in _NONE_COLUMNS:
        op.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} = 'None'")


def downgrade() -> None:
    pass
