"""add original-currency note to payments

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-05

EUR is the accounting currency: payments.amount always holds the EUR value that
counts toward income. When a tenant actually tendered a foreign currency we keep
that as a *note* only (orig_amount / orig_currency) — it is shown in tables and
on PDFs but never summed into a total, so reports can no longer mix currencies.

Backfill: any existing payment recorded in a non-EUR currency had its foreign
figure sitting in `amount`. Move that into the note columns and reset `amount`
to the contract's monthly rent (its EUR-equivalent), per the agreed default.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('orig_amount', sa.Numeric(10, 2), nullable=True))
    op.add_column('payments', sa.Column('orig_currency', sa.Text(), nullable=True))
    # Migrate existing foreign-currency payments: foreign figure → note columns,
    # amount → contract's monthly rent (EUR), currency → EUR.
    op.execute("""
        UPDATE payments p
        SET orig_amount   = p.amount,
            orig_currency = COALESCE(p.currency, 'EUR'),
            amount        = c.rent,
            currency      = 'EUR'
        FROM contracts c
        WHERE p.contract_id = c.id
          AND COALESCE(p.currency, 'EUR') <> 'EUR'
    """)


def downgrade() -> None:
    # Best-effort restore of the foreign figure into amount/currency.
    op.execute("""
        UPDATE payments
        SET amount   = orig_amount,
            currency = orig_currency
        WHERE orig_currency IS NOT NULL AND orig_currency <> 'EUR'
    """)
    op.drop_column('payments', 'orig_currency')
    op.drop_column('payments', 'orig_amount')
