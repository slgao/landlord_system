"""add handover_protocols, protocol_items and meter_readings.protocol_id

Revision ID: e2a9c4b17d53
Revises: c7d8e9f0a1b2
Create Date: 2026-09-02

The Wohnungsübergabeprotokoll: what was written down when the keys changed
hands, at Einzug and again at Auszug. Three pieces.

1. handover_protocols — one per handover. Not one per contract: a Nachbesichtigung
   after agreed repairs is a second Auszug protocol, and backdating the first one
   would destroy the evidence of what the flat looked like on the day.

2. protocol_items — the findings, discriminated by `kind`:
     'condition' — a room/element and its state ('ok' | 'wear' | 'defect')
     'key'       — a key type and how many were handed over
   One table with two nullable columns rather than two near-identical tables:
   both are per-protocol line items the landlord adds, reorders and deletes in
   the same way, and the UI shows them as two sections of one list.

   The 'ok' / 'wear' / 'defect' split is the legally load-bearing one, not
   decoration: normale Abnutzung (wear) may never be charged to the tenant,
   a Mangel (defect) may. That is why a defect carries estimated_cost — at
   Auszug it is precisely a candidate Kaution deduction.

3. meter_readings.protocol_id — the Zählerstände.
   A handover reading is not a private copy inside the protocol; it is a real
   meter_readings row that the Nebenkostenabrechnung reads like any other (it
   anchors the Tarifwechsel interpolation), merely tagged with the protocol it
   was taken at. Deleting a protocol therefore must NOT take the readings with
   it — they are billing data that outlives the document — hence SET NULL.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e2a9c4b17d53'
down_revision: Union[str, Sequence[str], None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # owner_id is the trailing column on every owned table — db.insert() relies
    # on that ordering (see the add_users_and_owner_id migration).
    op.create_table(
        'handover_protocols',
        sa.Column('id',              sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contract_id',     sa.Integer(), nullable=False),
        sa.Column('kind',            sa.Text(), nullable=False),   # 'move_in' | 'move_out'
        sa.Column('date',            sa.Text()),
        sa.Column('time',            sa.Text()),                   # optional clock time
        sa.Column('present_persons', sa.Text()),
        sa.Column('note',            sa.Text()),                   # general remarks
        sa.Column('signed',          sa.Integer(), server_default='0'),
        sa.Column('owner_id',        sa.Integer()),
    )
    op.create_index('ix_handover_protocols_contract_id', 'handover_protocols', ['contract_id'])
    op.create_foreign_key(
        'fk_handover_protocols_contract',
        'handover_protocols', 'contracts', ['contract_id'], ['id'], ondelete='CASCADE',
    )

    op.create_table(
        'protocol_items',
        sa.Column('id',             sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('protocol_id',    sa.Integer(), nullable=False),
        sa.Column('kind',           sa.Text(), nullable=False),    # 'condition' | 'key'
        sa.Column('area',           sa.Text()),                    # room/element, or key type
        sa.Column('condition',      sa.Text()),                    # conditions only
        sa.Column('quantity',       sa.Integer()),                 # keys only
        sa.Column('estimated_cost', sa.Numeric(10, 2)),            # defects only
        sa.Column('note',           sa.Text()),
        sa.Column('sort_order',     sa.Integer(), server_default='0'),
        sa.Column('owner_id',       sa.Integer()),
    )
    op.create_index('ix_protocol_items_protocol_id', 'protocol_items', ['protocol_id'])
    op.create_foreign_key(
        'fk_protocol_items_protocol',
        'protocol_items', 'handover_protocols', ['protocol_id'], ['id'], ondelete='CASCADE',
    )

    op.add_column('meter_readings', sa.Column('protocol_id', sa.Integer()))
    op.create_index('ix_meter_readings_protocol_id', 'meter_readings', ['protocol_id'])
    op.create_foreign_key(
        'fk_meter_readings_protocol',
        'meter_readings', 'handover_protocols', ['protocol_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_meter_readings_protocol', 'meter_readings', type_='foreignkey')
    op.drop_index('ix_meter_readings_protocol_id', table_name='meter_readings')
    op.drop_column('meter_readings', 'protocol_id')

    op.drop_constraint('fk_protocol_items_protocol', 'protocol_items', type_='foreignkey')
    op.drop_index('ix_protocol_items_protocol_id', table_name='protocol_items')
    op.drop_table('protocol_items')

    op.drop_constraint('fk_handover_protocols_contract', 'handover_protocols', type_='foreignkey')
    op.drop_index('ix_handover_protocols_contract_id', table_name='handover_protocols')
    op.drop_table('handover_protocols')
