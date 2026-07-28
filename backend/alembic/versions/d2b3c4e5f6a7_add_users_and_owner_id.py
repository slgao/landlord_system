"""add users table and owner_id multi-tenant isolation

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-28

Turns the single-password app into a multi-user SaaS:
- `users`: email (unique) + bcrypt password_hash. A user IS an owner.
- Every data table gains `owner_id` (FK users, ON DELETE CASCADE), nullable for
  now — a later migration enforces NOT NULL once all writers set it.
- `config` becomes per-user: its unique key changes from (key) to (owner_id,key).
- Backfill: all existing rows are assigned to a single seed user created from
  the current APP_PASSWORD_HASH / SEED_USER_EMAIL env (so the current data set
  carries over and the current password keeps working, now via email login).
"""
import os
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd2b3c4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every user-owned table. Excludes alembic_version (bookkeeping) and users.
OWNED_TABLES = [
    "apartments", "assistant_messages", "assistant_threads", "billing_profiles",
    "buildings", "co_tenants", "config", "contracts", "expenses", "flat_costs",
    "gas_meters", "heizung_meters", "kaution_deductions", "kaution_payments",
    "meter_readings", "mortgages", "payments", "properties",
    "property_tax_profiles", "reminders", "strom_meters", "tax_year_overrides",
    "tenants", "wasser_meters",
]


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=True),
        sa.Column('display_name', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.Text(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )

    for t in OWNED_TABLES:
        op.add_column(t, sa.Column('owner_id', sa.Integer(),
                      sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True))

    conn = op.get_bind()
    # Seed user from the current single-user credentials so existing data has an
    # owner and the current password keeps working (now as email login).
    email = os.environ.get("SEED_USER_EMAIL", "admin@vermio.local")
    pw_hash = os.environ.get("APP_PASSWORD_HASH", "") or None
    name = os.environ.get("APP_USERNAME", "admin")
    seed_id = conn.execute(sa.text(
        "INSERT INTO users (email, password_hash, display_name) "
        "VALUES (:e, :h, :n) RETURNING id"),
        {"e": email, "h": pw_hash, "n": name}).scalar()

    for t in OWNED_TABLES:
        conn.execute(sa.text(f"UPDATE {t} SET owner_id = :o"), {"o": seed_id})
        op.create_index(f"ix_{t}_owner_id", t, ["owner_id"])

    # config: make the key unique per-user instead of globally.
    conn.execute(sa.text(
        "ALTER TABLE config DROP CONSTRAINT IF EXISTS config_key_key"))
    conn.execute(sa.text(
        "ALTER TABLE config DROP CONSTRAINT IF EXISTS config_pkey"))
    # keep a surrogate; enforce (owner_id, key) uniqueness for upserts
    op.create_unique_constraint("uq_config_owner_key", "config", ["owner_id", "key"])


def downgrade() -> None:
    op.drop_constraint("uq_config_owner_key", "config", type_="unique")
    for t in OWNED_TABLES:
        op.drop_index(f"ix_{t}_owner_id", table_name=t)
        op.drop_column(t, "owner_id")
    op.drop_table('users')
