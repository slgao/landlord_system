"""add contract NK-Vorauszahlung and expense source_file

Revision ID: f1b2c3d4e5f6
Revises: e8f9a0b1c2d3
Create Date: 2026-07-19

- contracts.nebenkosten_vorauszahlung: monthly EUR portion of the (warm) rent
  that is a Nebenkosten prepayment. Lets the tax report split income into
  Kaltmiete and Umlagen (separate Anlage V lines).
- expenses.source_file: path of the scanned receipt/bill a cost row was
  extracted from (documents/<year>/<property>/...), for the audit trail.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contracts', sa.Column('nebenkosten_vorauszahlung', sa.Numeric(), nullable=True))
    op.add_column('expenses', sa.Column('source_file', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('expenses', 'source_file')
    op.drop_column('contracts', 'nebenkosten_vorauszahlung')
