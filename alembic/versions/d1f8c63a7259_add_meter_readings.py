"""add meter_readings table

Revision ID: d1f8c63a7259
Revises: e7a3b2f9d104
Create Date: 2026-04-16

Time-stamped meter readings, independent of any Nebenkostenabrechnung run.
Polymorphic over the four meter tables — meter_type tells you which one
meter_id refers to:
  - 'strom'   → strom_meters
  - 'gas'     → gas_meters
  - 'heizung' → heizung_meters
  - 'wasser'  → wasser_meters  (kalt/warm distinction lives on that table)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd1f8c63a7259'
down_revision: Union[str, Sequence[str], None] = 'e7a3b2f9d104'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'meter_readings',
        sa.Column('id',           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('meter_type',   sa.Text(),         nullable=False),
        sa.Column('meter_id',     sa.Integer(),      nullable=False),
        sa.Column('reading_date', sa.Text(),         nullable=False),
        sa.Column('reading',      sa.Numeric(12, 3), nullable=False),
        sa.Column('note',         sa.Text()),
    )
    op.create_index(
        'ix_meter_readings_meter',
        'meter_readings',
        ['meter_type', 'meter_id', 'reading_date'],
    )


def downgrade() -> None:
    op.drop_index('ix_meter_readings_meter', table_name='meter_readings')
    op.drop_table('meter_readings')
