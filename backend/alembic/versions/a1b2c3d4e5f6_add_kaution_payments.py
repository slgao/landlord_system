"""add kaution_payments table

Revision ID: a1b2c3d4e5f6
Revises: b9e7f2a4c8d6
Create Date: 2026-07-05

Ledger of Kaution installments actually received from the tenant. German law
lets a tenant pay the deposit in up to three monthly rates, so a contract's
single kaution_paid_date is not enough. The agreed total stays in
contracts.kaution_amount; the sum of these rows is the amount paid so far.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'b9e7f2a4c8d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kaution_payments',
        sa.Column('id',          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('date',        sa.Text()),
        sa.Column('amount',      sa.Numeric(10, 2)),
        sa.Column('note',        sa.Text()),
    )
    op.create_index(
        'ix_kaution_payments_contract_id',
        'kaution_payments',
        ['contract_id'],
    )
    op.create_foreign_key(
        'fk_kaution_payments_contract',
        'kaution_payments', 'contracts',
        ['contract_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_kaution_payments_contract', 'kaution_payments', type_='foreignkey')
    op.drop_index('ix_kaution_payments_contract_id', table_name='kaution_payments')
    op.drop_table('kaution_payments')
