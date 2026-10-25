"""The rent of a tenancy, period by period

Revision ID: d4e5f6a0b1c2
Revises: c3d4e5f6a0b1
Create Date: 2026-10-25

`contracts.rent` was one number used for every month of the tenancy, so
recording a rent increase restated the past. Raising a rent from 1.050 € to
1.150 € changed what had been expected in all twelve months of a filed tax
year, and with it the arrears history and every Mahnung built on it. The only
way to avoid that was to terminate the tenancy and enter a new one, which
breaks the Kaution, the deposit's interest and the Nebenkosten deadline chain.

Rent increases are routine here: §558 allows one every fifteen months, a
Staffelmiete (§557a) steps every year by agreement, an Indexmiete (§557b)
follows the Verbraucherpreisindex, and §559 allows a modernisation surcharge.
Each is the same tenancy at a new price from a given date — which is what flat
costs have always been able to say, with valid_from and valid_to.

So the periods become the record. Every existing contract gets one period,
starting the day the tenancy did and holding exactly what the contract holds
today, so nothing moves on the day this runs.

`contracts.rent` and `contracts.nebenkosten_vorauszahlung` stay where they are
and are no longer read: this migration copies out of them, never back into
them, and the application resolves the rent from the periods alone. Keeping two
records of the same money and choosing between them per page is how the
mortgage figures once drifted apart (see cost_types.py); the columns remain
only so that this revision can be stepped back without losing anything.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'contract_rents',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('contract_id', sa.Integer,
                  sa.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False),
        # The first day the price applies. Rent is due monthly in advance
        # (§556b), so the price in force on the first of a month is that
        # month's price.
        sa.Column('valid_from', sa.Text, nullable=False),
        sa.Column('rent', sa.Numeric(10, 2), nullable=False),
        # The Nebenkosten prepayment inside that rent. It moves with the price
        # — an increase usually raises both — so it belongs to the period
        # rather than to the contract.
        sa.Column('nebenkosten_vorauszahlung', sa.Numeric(10, 2), nullable=True),
        # Why this price: initial | agreed | staffel | index | modernisation.
        # The part a tenant can dispute, so the record has to carry it.
        sa.Column('kind', sa.Text, nullable=False, server_default='agreed'),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('owner_id', sa.Integer,
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
    )
    # Both are joined on, and an unindexed foreign key makes every join read
    # the whole table — see c3d4e5f6a0b1.
    op.create_index('ix_contract_rents_contract_id', 'contract_rents', ['contract_id'])
    op.create_index('ix_contract_rents_owner_id', 'contract_rents', ['owner_id'])
    # One price per start date per tenancy: two rows for the same day would be
    # the double-counting this is meant to prevent.
    op.create_index('ux_contract_rents_period', 'contract_rents',
                    ['contract_id', 'valid_from'], unique=True)

    # Every tenancy keeps exactly what it has today, dated from its start, so
    # no figure anywhere moves on the day this runs. A contract with no start
    # date (legacy rows) gets an empty valid_from, which reads as "has always
    # been in force".
    op.execute("""
        INSERT INTO contract_rents
            (contract_id, valid_from, rent, nebenkosten_vorauszahlung, kind, owner_id)
        SELECT c.id,
               COALESCE(NULLIF(c.start_date, 'None'), ''),
               COALESCE(c.rent, 0),
               c.nebenkosten_vorauszahlung,
               'initial',
               c.owner_id
        FROM contracts c
    """)


def downgrade() -> None:
    # Put the latest price back on the contract, so a step back keeps the
    # increases that were recorded while this revision was in place rather
    # than reverting every tenancy to what it was signed at.
    op.execute("""
        UPDATE contracts c
        SET rent = r.rent,
            nebenkosten_vorauszahlung = r.nebenkosten_vorauszahlung
        FROM (
            SELECT DISTINCT ON (contract_id) contract_id, rent, nebenkosten_vorauszahlung
            FROM contract_rents
            ORDER BY contract_id, valid_from DESC
        ) r
        WHERE r.contract_id = c.id
    """)
    op.drop_index('ux_contract_rents_period', table_name='contract_rents')
    op.drop_index('ix_contract_rents_owner_id', table_name='contract_rents')
    op.drop_index('ix_contract_rents_contract_id', table_name='contract_rents')
    op.drop_table('contract_rents')
