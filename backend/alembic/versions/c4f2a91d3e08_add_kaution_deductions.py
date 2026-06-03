"""add kaution_deductions table

Revision ID: c4f2a91d3e08
Revises: b8bbce64ae16
Create Date: 2026-04-16

Ledger of deductions taken from a contract's Kaution (e.g. Nebenkosten
Nachzahlung verrechnet, damages, cleaning). The amount returned to the
tenant becomes: kaution_amount − Σ deductions.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c4f2a91d3e08'
down_revision: Union[str, Sequence[str], None] = 'b8bbce64ae16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kaution_deductions',
        sa.Column('id',             sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contract_id',    sa.Integer(), nullable=False),
        sa.Column('date',           sa.Text()),
        sa.Column('amount',         sa.Numeric(10, 2)),
        sa.Column('category',       sa.Text()),
        sa.Column('reason',         sa.Text()),
        sa.Column('reference_type', sa.Text()),
        sa.Column('reference_id',   sa.Integer()),
    )
    op.create_index(
        'ix_kaution_deductions_contract_id',
        'kaution_deductions',
        ['contract_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_kaution_deductions_contract_id', table_name='kaution_deductions')
    op.drop_table('kaution_deductions')
