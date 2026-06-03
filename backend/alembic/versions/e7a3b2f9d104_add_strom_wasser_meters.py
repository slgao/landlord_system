"""add strom_meters and wasser_meters

Revision ID: e7a3b2f9d104
Revises: c4f2a91d3e08
Create Date: 2026-04-16

Per-apartment electricity and water meters with Zählernummer.
- strom_meters: usually one per apartment (multiple still allowed).
- wasser_meters: typically one Kaltwasserzähler and one or more
  Warmwasserzähler per apartment (type='kalt' | 'warm').
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e7a3b2f9d104'
down_revision: Union[str, Sequence[str], None] = 'c4f2a91d3e08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'strom_meters',
        sa.Column('id',            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('apartment_id',  sa.Integer(), nullable=False),
        sa.Column('serial_number', sa.Text()),
        sa.Column('description',   sa.Text()),
    )
    op.create_index(
        'ix_strom_meters_apartment_id',
        'strom_meters',
        ['apartment_id'],
    )
    op.create_table(
        'wasser_meters',
        sa.Column('id',            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('apartment_id',  sa.Integer(), nullable=False),
        sa.Column('serial_number', sa.Text()),
        sa.Column('description',   sa.Text()),
        sa.Column('type',          sa.Text(), nullable=False, server_default='kalt'),
    )
    op.create_index(
        'ix_wasser_meters_apartment_id',
        'wasser_meters',
        ['apartment_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_wasser_meters_apartment_id', table_name='wasser_meters')
    op.drop_table('wasser_meters')
    op.drop_index('ix_strom_meters_apartment_id', table_name='strom_meters')
    op.drop_table('strom_meters')
