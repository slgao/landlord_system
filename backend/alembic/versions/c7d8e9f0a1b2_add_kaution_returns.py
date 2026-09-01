"""add kaution_returns table

Revision ID: c7d8e9f0a1b2
Revises: a4c7e91b2d68
Create Date: 2026-09-02

Ledger of deposit money paid back to the tenant. A deposit is often released in
two steps: part right after the handover once the flat is seen to be undamaged,
the rest once the final Nebenkostenabrechnung is settled. The single
contracts.kaution_returned_date/amount pair could only record one of those, so a
partial release looked like a closed case — the remainder still held became
invisible, and the deposit could no longer be offset against a Nachzahlung.

Those two columns stay, now derived: the amount mirrors the sum of these rows,
and the date is set only once nothing is still held. Every "is the deposit still
with me?" check in the app keys off that date, and now answers correctly during
a partial release.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'a4c7e91b2d68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # owner_id is the trailing column on every owned table — db.insert() relies
    # on that ordering (see the add_users_and_owner_id migration).
    op.create_table(
        'kaution_returns',
        sa.Column('id',          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('date',        sa.Text()),
        sa.Column('amount',      sa.Numeric(10, 2)),
        sa.Column('note',        sa.Text()),
        sa.Column('owner_id',    sa.Integer()),
    )
    op.create_index('ix_kaution_returns_contract_id', 'kaution_returns', ['contract_id'])
    op.create_foreign_key(
        'fk_kaution_returns_contract',
        'kaution_returns', 'contracts', ['contract_id'], ['id'], ondelete='CASCADE',
    )

    # Carry every return already recorded on a contract into the ledger, so an
    # existing repayment keeps showing up instead of reading as "nothing returned".
    op.execute("""
        INSERT INTO kaution_returns (contract_id, date, amount, note, owner_id)
        SELECT id, kaution_returned_date, kaution_returned_amount,
               'Übernommen aus dem Vertrag', owner_id
        FROM contracts
        WHERE kaution_returned_amount IS NOT NULL
          AND kaution_returned_date IS NOT NULL
          AND kaution_returned_date <> 'None'
    """)

    # A contract whose recorded return did not settle the whole balance was
    # nonetheless flagged as returned. Clear the date on those so they read as
    # partially released; the amount stays as the running total.
    op.execute("""
        UPDATE contracts c SET kaution_returned_date = NULL
        WHERE c.kaution_returned_date IS NOT NULL
          AND c.kaution_returned_date <> 'None'
          AND COALESCE(c.kaution_amount, 0)
              - COALESCE((SELECT SUM(amount) FROM kaution_deductions d WHERE d.contract_id = c.id), 0)
              - COALESCE(c.kaution_returned_amount, 0) > 0.005
    """)


def downgrade() -> None:
    # Restore the flag for anything the upgrade cleared, then drop the ledger.
    op.execute("""
        UPDATE contracts c SET kaution_returned_date = (
            SELECT MAX(date) FROM kaution_returns r WHERE r.contract_id = c.id
        )
        WHERE c.kaution_returned_date IS NULL
          AND EXISTS (SELECT 1 FROM kaution_returns r WHERE r.contract_id = c.id)
    """)
    op.drop_constraint('fk_kaution_returns_contract', 'kaution_returns', type_='foreignkey')
    op.drop_index('ix_kaution_returns_contract_id', table_name='kaution_returns')
    op.drop_table('kaution_returns')
