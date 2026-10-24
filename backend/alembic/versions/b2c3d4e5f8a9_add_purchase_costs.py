"""Kaufnebenkosten, so the equity actually put into a flat can be worked out

Revision ID: b2c3d4e5f8a9
Revises: a1b2c3d4e5f7
Create Date: 2026-10-24

The Kaufpreis is already on file — property_tax_profiles.purchase_price, where
the AfA reads it — so the equity a flat was bought with is nearly derivable:

    Eigenkapital = Kaufpreis + Kaufnebenkosten − Darlehenssumme

Nearly, because without the Nebenkosten it comes out wrong, and not subtly. Of
the five owned flats here, two land on exactly 0 and one on −1.000 €: the loan
was larger than the purchase price because it also covered the Grunderwerb-
steuer and the notary. An Eigenkapitalrendite computed on 0 or a negative
number is not a number at all.

In Berlin these run to roughly a tenth of the price — Grunderwerbsteuer 6 %,
Notar and Grundbuch about 2 %, a Makler another 3,57 % where there was one —
but they are not derivable from anything on file, so the column stays empty
until the landlord fills it in rather than being seeded with a guess at what
their own purchase cost.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f8a9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('property_tax_profiles',
                  sa.Column('purchase_costs', sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('property_tax_profiles', 'purchase_costs')
