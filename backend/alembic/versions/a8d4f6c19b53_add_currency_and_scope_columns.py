"""add currency and scope columns

Revision ID: a8d4f6c19b53
Revises: f3a1c9e82b47
Create Date: 2026-05-02

Catch-up migration that captures columns previously added imperatively in
db.init_db() so Alembic becomes the single source of truth for the schema.

- payments.currency, contracts.currency, contracts.kaution_currency (VARCHAR(3))
- {heizung,gas,strom,wasser}_meters.scope (VARCHAR(10))

Uses raw SQL with IF NOT EXISTS so it is safe to run on databases that
already have these columns from a prior init_db() invocation.
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'a8d4f6c19b53'
down_revision: Union[str, Sequence[str], None] = 'f3a1c9e82b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE payments       ADD COLUMN IF NOT EXISTS currency         VARCHAR(3)  DEFAULT 'EUR'")
    op.execute("ALTER TABLE contracts      ADD COLUMN IF NOT EXISTS currency         VARCHAR(3)  DEFAULT 'EUR'")
    op.execute("ALTER TABLE contracts      ADD COLUMN IF NOT EXISTS kaution_currency VARCHAR(3)  DEFAULT 'EUR'")
    op.execute("ALTER TABLE heizung_meters ADD COLUMN IF NOT EXISTS scope            VARCHAR(10) DEFAULT 'room'")
    op.execute("ALTER TABLE gas_meters     ADD COLUMN IF NOT EXISTS scope            VARCHAR(10) DEFAULT 'shared'")
    op.execute("ALTER TABLE strom_meters   ADD COLUMN IF NOT EXISTS scope            VARCHAR(10) DEFAULT 'shared'")
    op.execute("ALTER TABLE wasser_meters  ADD COLUMN IF NOT EXISTS scope            VARCHAR(10) DEFAULT 'shared'")


def downgrade() -> None:
    op.execute("ALTER TABLE wasser_meters  DROP COLUMN IF EXISTS scope")
    op.execute("ALTER TABLE strom_meters   DROP COLUMN IF EXISTS scope")
    op.execute("ALTER TABLE gas_meters     DROP COLUMN IF EXISTS scope")
    op.execute("ALTER TABLE heizung_meters DROP COLUMN IF EXISTS scope")
    op.execute("ALTER TABLE contracts      DROP COLUMN IF EXISTS kaution_currency")
    op.execute("ALTER TABLE contracts      DROP COLUMN IF EXISTS currency")
    op.execute("ALTER TABLE payments       DROP COLUMN IF EXISTS currency")
