"""a meter reading can be witnessed at more than one handover

Revision ID: f4b6d82e05a1
Revises: e2a9c4b17d53
Create Date: 2026-09-02

When a tenancy is handed straight on, the outgoing tenant's Auszug and the
incoming tenant's Einzug happen the same afternoon at the same meter — one
physical reading, recorded twice. meter_readings.protocol_id could only name one
protocol, so the second handover's sheet showed nothing and the Meter Readings
page grew a duplicate row for a single observation.

The link becomes many-to-many. The invariant the app now keeps is one reading per
meter per date; which handovers witnessed it is a set.

Deliberately NOT merged: two readings of the same meter with the same value on
*different* dates. A Heizkostenverteiler in an unused room can read the same at
Einzug and Auszug two years apart, and collapsing those would delete one endpoint
of the billing period, leaving the Nebenkostenabrechnung with no start or no end
for that meter. Same value is not the same observation — same date is.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f4b6d82e05a1'
down_revision: Union[str, Sequence[str], None] = 'e2a9c4b17d53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # owner_id trailing, per the db.insert() convention.
    op.create_table(
        'meter_reading_protocols',
        sa.Column('id',          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('reading_id',  sa.Integer(), nullable=False),
        sa.Column('protocol_id', sa.Integer(), nullable=False),
        sa.Column('owner_id',    sa.Integer()),
    )
    op.create_index('ux_meter_reading_protocols', 'meter_reading_protocols',
                    ['reading_id', 'protocol_id'], unique=True)
    op.create_index('ix_mrp_protocol_id', 'meter_reading_protocols', ['protocol_id'])
    op.create_foreign_key('fk_mrp_reading', 'meter_reading_protocols',
                          'meter_readings', ['reading_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_mrp_protocol', 'meter_reading_protocols',
                          'handover_protocols', ['protocol_id'], ['id'], ondelete='CASCADE')

    # Carry the existing single links across.
    op.execute("""
        INSERT INTO meter_reading_protocols (reading_id, protocol_id, owner_id)
        SELECT id, protocol_id, owner_id FROM meter_readings WHERE protocol_id IS NOT NULL
    """)

    # Fold duplicates that already exist. Only where the meter, the date AND the
    # value all match, so the merge cannot lose a number; and only in groups that
    # a handover took part in, so two deliberate manual readings are left alone.
    # The survivor is the row carrying a note — that is the one with the
    # landlord's own words on it ("Yunkun Rui - Einzugsablesung") — falling back
    # to the oldest id.
    op.execute("""
        CREATE TEMPORARY TABLE _dupes AS
        WITH ranked AS (
            SELECT id, owner_id, meter_type, meter_id, reading_date, reading,
                   FIRST_VALUE(id) OVER (
                       PARTITION BY owner_id, meter_type, meter_id, reading_date, reading
                       ORDER BY (CASE WHEN note IS NOT NULL AND note <> '' THEN 0 ELSE 1 END), id
                   ) AS keep_id
            FROM meter_readings
            WHERE (owner_id, meter_type, meter_id, reading_date, reading) IN (
                SELECT owner_id, meter_type, meter_id, reading_date, reading
                FROM meter_readings
                GROUP BY owner_id, meter_type, meter_id, reading_date, reading
                HAVING COUNT(*) > 1
                   AND COUNT(protocol_id) > 0
            )
        )
        SELECT id, keep_id FROM ranked WHERE id <> keep_id
    """)
    # Point every protocol link at the survivor, then drop the redundant rows.
    op.execute("""
        UPDATE meter_reading_protocols mrp SET reading_id = d.keep_id
        FROM _dupes d WHERE mrp.reading_id = d.id
          AND NOT EXISTS (SELECT 1 FROM meter_reading_protocols x
                          WHERE x.reading_id = d.keep_id AND x.protocol_id = mrp.protocol_id)
    """)
    op.execute("DELETE FROM meter_reading_protocols mrp USING _dupes d WHERE mrp.reading_id = d.id")
    op.execute("DELETE FROM meter_readings m USING _dupes d WHERE m.id = d.id")
    op.execute("DROP TABLE _dupes")

    # protocol_id would now be a second, drifting source of truth.
    op.drop_constraint('fk_meter_readings_protocol', 'meter_readings', type_='foreignkey')
    op.drop_index('ix_meter_readings_protocol_id', table_name='meter_readings')
    op.drop_column('meter_readings', 'protocol_id')


def downgrade() -> None:
    op.add_column('meter_readings', sa.Column('protocol_id', sa.Integer()))
    op.create_index('ix_meter_readings_protocol_id', 'meter_readings', ['protocol_id'])
    op.create_foreign_key('fk_meter_readings_protocol', 'meter_readings',
                          'handover_protocols', ['protocol_id'], ['id'], ondelete='SET NULL')
    # A merged reading can only name one protocol again; keep the earliest. The
    # rows folded together on the way up are not recoverable — they were exact
    # duplicates, so nothing is lost but the duplication itself.
    op.execute("""
        UPDATE meter_readings m SET protocol_id = (
            SELECT MIN(protocol_id) FROM meter_reading_protocols p WHERE p.reading_id = m.id
        )
    """)
    op.drop_constraint('fk_mrp_protocol', 'meter_reading_protocols', type_='foreignkey')
    op.drop_constraint('fk_mrp_reading', 'meter_reading_protocols', type_='foreignkey')
    op.drop_index('ix_mrp_protocol_id', table_name='meter_reading_protocols')
    op.drop_index('ux_meter_reading_protocols', table_name='meter_reading_protocols')
    op.drop_table('meter_reading_protocols')
