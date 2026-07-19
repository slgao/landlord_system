"""add tax module tables

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-19

Anlage-V helper (docs/PRD-tax-module.md):
- property_tax_profiles: one-time purchase/AfA data per property
- mortgages: annuity-loan terms per property -> computed Schuldzinsen per year
- expenses: one-off deductible costs (repairs, insurance, ...), optionally
  spread over 2-5 years (§82b EStDV)
- tax_year_overrides: manually entered figures for years without payment
  records (2025), keyed by (property, year, field)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'property_tax_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('purchase_date', sa.Text(), nullable=True),
        sa.Column('purchase_price', sa.Numeric(), nullable=True),
        sa.Column('building_share_pct', sa.Numeric(), nullable=True),
        sa.Column('afa_rate_pct', sa.Numeric(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
    )
    op.create_table(
        'mortgages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('principal', sa.Numeric(), nullable=False),
        sa.Column('interest_rate_pct', sa.Numeric(), nullable=False),
        sa.Column('tilgung_rate_pct', sa.Numeric(), nullable=False),
        sa.Column('start_date', sa.Text(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
    )
    op.create_table(
        'expenses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('apartment_id', sa.Integer(), sa.ForeignKey('apartments.id'), nullable=True),
        sa.Column('expense_date', sa.Text(), nullable=False),
        sa.Column('amount', sa.Numeric(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('vendor', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('deductible', sa.Integer(), server_default='1'),
        sa.Column('distribute_years', sa.Integer(), server_default='1'),
    )
    op.create_table(
        'tax_year_overrides',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('property_id', sa.Integer(), sa.ForeignKey('properties.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('field', sa.Text(), nullable=False),
        sa.Column('value', sa.Numeric(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.UniqueConstraint('property_id', 'tax_year', 'field', name='uq_tax_override'),
    )


def downgrade() -> None:
    op.drop_table('tax_year_overrides')
    op.drop_table('expenses')
    op.drop_table('mortgages')
    op.drop_table('property_tax_profiles')
