"""land values from Berlin's open data, and what a flat is worth on top of them

Revision ID: a1b2c3d4e5f7
Revises: d0e1f2a3b4c5
Create Date: 2026-10-24

Equity is value less debt, and no property had a value on file — so the
Financing page's equity and LTV were dark for the whole portfolio. There is no
real-time valuation to be had for German property, but there is official open
data, and it is enough to keep a defensible figure:

- Bodenrichtwerte (Berlin, Datenlizenz Deutschland Zero 2.0) give the land
  value per m² for the zone a house stands in, at a yearly Stichtag. Fetched
  per property on demand and kept here with that Stichtag, so a figure can
  always be traced to the day it was official.
- A comparable €/m² of living space is what actually values a condo
  (Vergleichswertverfahren). The Gutachterausschuss publishes these per
  district once a year; the column holds the one in force for this flat and
  stays editable, because only the owner knows the fit-out and floor.

`land_values` keeps one row per property and Stichtag rather than overwriting,
so the land value's own history is visible — the point of an annual series.

New columns on `properties`:

- owned              — whether this flat is the landlord's own. Some flats here
                       are managed but not owned: their rent and meters are
                       tracked like any other, but their value is not his asset
                       and must stay out of the portfolio's worth and equity.
                       Default 1, because everything already on file is owned.
- living_sqm         — the unit's Wohnfläche. Not derived from its apartments:
                       a WG's rooms do not sum to the flat's area (hallway,
                       kitchen and bath belong to none of them), and two
                       properties here have rooms with no size at all.
- plot_sqm           — Grundstücksfläche, for the land share of a
                       Wohnungseigentum (BRW × plot × MEA). Optional: without
                       it the land value is still reported per m² of floor
                       space via the zone's GFZ.
- comparable_per_sqm — the €/m² the valuation uses.
- valuation_note     — where that comparable came from, in the owner's words.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('properties', sa.Column('owned', sa.Integer(), nullable=False,
                                          server_default='1'))
    op.add_column('properties', sa.Column('living_sqm', sa.Numeric(10, 2), nullable=True))
    op.add_column('properties', sa.Column('plot_sqm', sa.Numeric(10, 2), nullable=True))
    op.add_column('properties', sa.Column('comparable_per_sqm', sa.Numeric(10, 2), nullable=True))
    op.add_column('properties', sa.Column('valuation_note', sa.Text(), nullable=True))

    op.create_table(
        'land_values',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('property_id', sa.Integer(), nullable=False),
        # The official valuation date, e.g. '2026-01-01'. Part of the key:
        # a new year is a new row, not an overwrite.
        sa.Column('stichtag', sa.Text(), nullable=False),
        sa.Column('brw', sa.Numeric(12, 2), nullable=False),      # € per m² of land
        sa.Column('gfz', sa.Numeric(6, 3), nullable=True),        # Geschossflächenzahl
        sa.Column('nutzung', sa.Text(), nullable=True),           # 'W - Wohngebiet', …
        sa.Column('beitragszustand', sa.Text(), nullable=True),
        sa.Column('bezirk', sa.Text(), nullable=True),
        sa.Column('ortsteil', sa.Text(), nullable=True),
        sa.Column('zone_id', sa.Text(), nullable=True),           # brwid, to re-find the zone
        # The house coordinate the zone was read at, in EPSG:25833 — the CRS
        # both Berlin services speak. Kept so a lookup is reproducible without
        # geocoding the address again.
        sa.Column('east', sa.Numeric(12, 2), nullable=True),
        sa.Column('north', sa.Numeric(12, 2), nullable=True),
        sa.Column('matched_address', sa.Text(), nullable=True),   # what the register matched
        sa.Column('source', sa.Text(), nullable=True),
        sa.Column('fetched_at', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.Integer()),
    )
    op.create_index('ix_land_values_property_id', 'land_values', ['property_id'])
    op.create_index('ix_land_values_owner_id', 'land_values', ['owner_id'])
    op.create_unique_constraint('uq_land_value_stichtag', 'land_values',
                                ['property_id', 'stichtag'])
    op.create_foreign_key('fk_land_values_property', 'land_values', 'properties',
                          ['property_id'], ['id'], ondelete='CASCADE')

    # A single-flat property's Wohnfläche is already on its one apartment;
    # carry it over so the valuation works without re-typing it. A WG is left
    # blank on purpose: its rooms do not sum to the flat's area.
    op.execute("""
        UPDATE properties p SET living_sqm = a.size_sqm
        FROM (SELECT property_id, MIN(size_sqm) AS size_sqm
              FROM apartments GROUP BY property_id HAVING COUNT(*) = 1) a
        WHERE a.property_id = p.id AND a.size_sqm IS NOT NULL AND p.living_sqm IS NULL
    """)


def downgrade() -> None:
    op.drop_table('land_values')
    for col in ('valuation_note', 'comparable_per_sqm', 'plot_sqm', 'living_sqm', 'owned'):
        op.drop_column('properties', col)
