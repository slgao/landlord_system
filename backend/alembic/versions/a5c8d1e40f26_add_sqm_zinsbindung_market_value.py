"""add flat size, Zinsbindung and market value

Revision ID: a5c8d1e40f26
Revises: f4b6d82e05a1
Create Date: 2026-09-12

Three figures the portfolio could not answer questions with:

- apartments.size_sqm — without it there is no €/m², so no comparison against
  the Mietspiegel and no read on whether a flat could carry another room.
- mortgages.fixed_until / follow_up_rate_pct — the Zinsbindung. Every schedule
  assumed today's Sollzins held to payoff, which for a 2018 loan at 1.44 %
  projected a rate that expires in 2028 out to 2045.
- properties.market_value / market_value_date — equity is value less debt, and
  only the purchase price was on file, so equity was guesswork.

All nullable: a portfolio that has not filled them in behaves exactly as before.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a5c8d1e40f26'
down_revision: Union[str, Sequence[str], None] = 'f4b6d82e05a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('apartments', sa.Column('size_sqm', sa.Numeric(), nullable=True))
    # Date columns are TEXT (ISO) everywhere in this schema; keep that.
    op.add_column('mortgages', sa.Column('fixed_until', sa.Text(), nullable=True))
    op.add_column('mortgages', sa.Column('follow_up_rate_pct', sa.Numeric(), nullable=True))
    op.add_column('properties', sa.Column('market_value', sa.Numeric(), nullable=True))
    op.add_column('properties', sa.Column('market_value_date', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('properties', 'market_value_date')
    op.drop_column('properties', 'market_value')
    op.drop_column('mortgages', 'follow_up_rate_pct')
    op.drop_column('mortgages', 'fixed_until')
    op.drop_column('apartments', 'size_sqm')
