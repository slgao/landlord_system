"""add buildings table and WE (Wohnungseigentum) attributes on properties

Revision ID: c1a2b3d4e5f6
Revises: a2c4e6f80b13
Create Date: 2026-07-28

Splits the address off into a normalized `buildings` table so several
Wohnungseigentum units (WEs) can share one physical address without being
merged into a single tax-declaration unit. A `property` now models exactly
one WE = one Anlage V; a `building` groups WEs and owns the postal address.

- buildings: id, name, street, house_no, zip, city, notes, created_at
- properties gains: building_id (FK), we_label (e.g. "WE 3"), mea (Miteigentums-
  anteil, e.g. 250/1000 -> 0.25 as a fraction or the raw tenths — stored as
  NUMERIC, interpretation is display-only).

`properties.name` and `properties.address` are kept as-is (legacy/denormalized
mirror) so the ~25 existing call sites keep working; the canonical address now
lives on the building. Backfill creates one building per distinct property
address (COALESCE(address, name)); properties sharing an address share a
building automatically.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'a2c4e6f80b13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'buildings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('street', sa.Text(), nullable=True),
        sa.Column('house_no', sa.Text(), nullable=True),
        sa.Column('zip', sa.Text(), nullable=True),
        sa.Column('city', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.add_column('properties', sa.Column('building_id', sa.Integer(),
                  sa.ForeignKey('buildings.id', ondelete='SET NULL'), nullable=True))
    op.add_column('properties', sa.Column('we_label', sa.Text(), nullable=True))
    op.add_column('properties', sa.Column('mea', sa.Numeric(), nullable=True))

    # Backfill: one building per distinct address; link every property to it.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, name, address FROM properties ORDER BY id")).fetchall()
    building_by_key: dict[str, int] = {}
    for pid, name, address in rows:
        key = ((address or name or "").strip()) or f"__p{pid}"
        bid = building_by_key.get(key)
        if bid is None:
            bid = conn.execute(sa.text(
                "INSERT INTO buildings (name, street) VALUES (:n, :s) RETURNING id"),
                {"n": (name or address or key), "s": address}).scalar()
            building_by_key[key] = bid
        conn.execute(sa.text("UPDATE properties SET building_id = :b WHERE id = :p"),
                     {"b": bid, "p": pid})


def downgrade() -> None:
    op.drop_column('properties', 'mea')
    op.drop_column('properties', 'we_label')
    op.drop_column('properties', 'building_id')
    op.drop_table('buildings')
