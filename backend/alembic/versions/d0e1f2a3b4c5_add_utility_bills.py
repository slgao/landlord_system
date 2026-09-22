"""provider bills on expenses, linked to tenant settlements

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-22

The Rechnungen behind a Nebenkostenabrechnung: the Strom or Gas supplier's
Jahresabrechnung, the water bill, the Hausgeldabrechnung for the
Betriebskosten. Each arrives on its own schedule, and a tenant's Abrechnung
may cover one of them or several at once — so bills and settlements are
many-to-many.

A bill is an expenses row, not a table of its own: what you paid (the
Nachzahlung, or a negative Guthaben) is an expense in the year it moved, and
the tax report, Belegliste and balance sheet already treat expenses right.
The new columns only describe it as a bill:

- utility       — what it bills; set means "this is a provider bill"
- period_start / period_end — the billing period, which is what a tenant
                  Abrechnung is matched against
- bill_total    — the period's total cost as stated on the bill; the
                  expense amount is only the part beyond the Abschläge
- tenant_settled — your call that the bill is fully passed on. Not derived:
                  a WG bill is shared by several tenants, and only you know
                  when the last of them has been settled
- pdf           — the bill itself

nk_settlement_bills links a tenant settlement to the bills it covers.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('expenses', sa.Column('utility', sa.Text(), nullable=True))
    op.add_column('expenses', sa.Column('period_start', sa.Text(), nullable=True))
    op.add_column('expenses', sa.Column('period_end', sa.Text(), nullable=True))
    op.add_column('expenses', sa.Column('bill_total', sa.Numeric(10, 2), nullable=True))
    op.add_column('expenses', sa.Column('tenant_settled', sa.Integer(), nullable=False,
                                        server_default='0'))
    op.add_column('expenses', sa.Column('pdf', sa.LargeBinary(), nullable=True))

    op.create_table(
        'nk_settlement_bills',
        sa.Column('settlement_id', sa.Integer(), nullable=False),
        sa.Column('expense_id',    sa.Integer(), nullable=False),
        sa.Column('owner_id',      sa.Integer()),
        sa.PrimaryKeyConstraint('settlement_id', 'expense_id'),
    )
    op.create_index('ix_nk_settlement_bills_expense_id', 'nk_settlement_bills', ['expense_id'])
    op.create_foreign_key('fk_nk_settlement_bills_settlement', 'nk_settlement_bills',
                          'nk_settlements', ['settlement_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_nk_settlement_bills_expense', 'nk_settlement_bills',
                          'expenses', ['expense_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_table('nk_settlement_bills')
    for col in ('pdf', 'tenant_settled', 'bill_total', 'period_end', 'period_start', 'utility'):
        op.drop_column('expenses', col)
