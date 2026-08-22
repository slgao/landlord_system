"""add phone to tenants

Revision ID: a4c7e91b2d68
Revises: d2b3c4e5f6a7
Create Date: 2026-08-22

A tenant's phone number, alongside their email. Optional — most contact still
happens in writing, but a number is what you reach for when a Handwerker needs
access to the flat at short notice.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a4c7e91b2d68'
down_revision: Union[str, Sequence[str], None] = 'd2b3c4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('phone', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('tenants', 'phone')
