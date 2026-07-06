"""add rent_settled_until to contracts

Revision ID: c5d6e7f8a9b0
Revises: b2c3d4e5f6a7
Create Date: 2026-07-06

Per-contract "rent is settled through this date" marker for the payment-reminder
calculation. When set, the reminders logic treats every month up to and
including that date as paid (useful when old payments were never recorded) and
only evaluates months after it. NULL means "no manual settlement — use the
default look-back window".
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contracts', sa.Column('rent_settled_until', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('contracts', 'rent_settled_until')
