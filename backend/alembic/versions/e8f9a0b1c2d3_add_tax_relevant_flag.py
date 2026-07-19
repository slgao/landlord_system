"""add tax_relevant flag to properties

Revision ID: e8f9a0b1c2d3
Revises: d6e7f8a9b0c1
Create Date: 2026-07-19

Not every managed property belongs to the user (some are managed for others),
so each property can be excluded from the Anlage-V tax report. Default 1:
included.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, Sequence[str], None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('properties', sa.Column('tax_relevant', sa.Integer(), server_default='1'))


def downgrade() -> None:
    op.drop_column('properties', 'tax_relevant')
