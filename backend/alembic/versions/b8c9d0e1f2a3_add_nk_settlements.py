"""add nk_settlements, payments.kind and payments.settlement_id

Revision ID: b8c9d0e1f2a3
Revises: a5c8d1e40f26
Create Date: 2026-09-22

The Nebenkostenabrechnung sent to a tenant, and the money that moves because
of it.

1. nk_settlements — one per Abrechnung: which contract, which billing period,
   the result, when it went out, and the PDF as sent. `amount` is signed from
   the landlord's side: positive is a Nachzahlung the tenant owes, negative a
   Guthaben to pay back. Nothing about it is "open" or "paid" in the table;
   that is derived from the payments linked to it, so it cannot drift.

2. payments.kind — 'rent' (the default, and every existing row) or
   'nk_settlement'. Until now a settlement payment could only be entered as
   rent, where it counted as credit against rent owed (hiding a missed month)
   and landed on the Kaltmiete line of Anlage V instead of Umlagen. A refund
   could not be entered at all without looking like missing rent.

3. payments.settlement_id — which Abrechnung a settlement payment belongs to.
   SET NULL on delete: the money still moved when the record is removed.

The columns land after owner_id, so payments inserts name their columns
rather than relying on db.insert()'s positional owner_id-last convention.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a5c8d1e40f26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'nk_settlements',
        sa.Column('id',           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contract_id',  sa.Integer(), nullable=False),
        # Dates are TEXT (ISO) everywhere in this schema; keep that.
        sa.Column('period_start', sa.Text(), nullable=False),
        sa.Column('period_end',   sa.Text(), nullable=False),
        sa.Column('amount',       sa.Numeric(10, 2), nullable=False),
        sa.Column('issued_date',  sa.Text()),
        sa.Column('note',         sa.Text()),
        sa.Column('pdf',          sa.LargeBinary()),
        sa.Column('owner_id',     sa.Integer()),
    )
    op.create_index('ix_nk_settlements_contract_id', 'nk_settlements', ['contract_id'])
    op.create_foreign_key(
        'fk_nk_settlements_contract',
        'nk_settlements', 'contracts', ['contract_id'], ['id'], ondelete='CASCADE',
    )

    op.add_column('payments', sa.Column('kind', sa.Text(), nullable=False,
                                        server_default='rent'))
    op.create_check_constraint('ck_payments_kind', 'payments',
                               "kind IN ('rent', 'nk_settlement')")
    op.add_column('payments', sa.Column('settlement_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_payments_settlement',
        'payments', 'nk_settlements', ['settlement_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_payments_settlement_id', 'payments', ['settlement_id'])


def downgrade() -> None:
    op.drop_index('ix_payments_settlement_id', 'payments')
    op.drop_constraint('fk_payments_settlement', 'payments', type_='foreignkey')
    op.drop_column('payments', 'settlement_id')
    op.drop_constraint('ck_payments_kind', 'payments', type_='check')
    op.drop_column('payments', 'kind')
    op.drop_constraint('fk_nk_settlements_contract', 'nk_settlements', type_='foreignkey')
    op.drop_index('ix_nk_settlements_contract_id', 'nk_settlements')
    op.drop_table('nk_settlements')
