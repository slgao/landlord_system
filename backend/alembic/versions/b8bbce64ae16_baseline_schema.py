"""baseline_schema

Revision ID: b8bbce64ae16
Revises:
Create Date: 2026-04-08

Full schema baseline — all tables as of the SQLite → PostgreSQL migration.
Running `alembic upgrade head` on a fresh database brings it to current state.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b8bbce64ae16'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'properties',
        sa.Column('id',      sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name',    sa.Text()),
        sa.Column('address', sa.Text()),
    )
    op.create_table(
        'apartments',
        sa.Column('id',          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('property_id', sa.Integer()),
        sa.Column('name',        sa.Text()),
        sa.Column('flat',        sa.Text()),
    )
    op.create_table(
        'tenants',
        sa.Column('id',     sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name',   sa.Text()),
        sa.Column('email',  sa.Text()),
        sa.Column('gender', sa.Text(), server_default='diverse'),
    )
    op.create_table(
        'contracts',
        sa.Column('id',                      sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id',               sa.Integer()),
        sa.Column('apartment_id',            sa.Integer()),
        sa.Column('rent',                    sa.Numeric(10, 2)),
        sa.Column('start_date',              sa.Text()),
        sa.Column('end_date',                sa.Text()),
        sa.Column('kaution_amount',          sa.Numeric(10, 2)),
        sa.Column('kaution_paid_date',       sa.Text()),
        sa.Column('kaution_returned_date',   sa.Text()),
        sa.Column('kaution_returned_amount', sa.Numeric(10, 2)),
        sa.Column('terminated',              sa.Integer(), server_default='0'),
    )
    op.create_table(
        'payments',
        sa.Column('id',           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contract_id',  sa.Integer()),
        sa.Column('amount',       sa.Numeric(10, 2)),
        sa.Column('payment_date', sa.Text()),
    )
    op.create_table(
        'flat_costs',
        sa.Column('id',           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('apartment_id', sa.Integer()),
        sa.Column('cost_type',    sa.Text()),
        sa.Column('amount',       sa.Numeric(10, 2)),
        sa.Column('frequency',    sa.Text()),
        sa.Column('valid_from',   sa.Text()),
        sa.Column('valid_to',     sa.Text()),
    )
    op.create_table(
        'reminders',
        sa.Column('id',          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contract_id', sa.Integer()),
        sa.Column('sent_date',   sa.Text()),
        sa.Column('months_due',  sa.Text()),
        sa.Column('amount_due',  sa.Numeric(10, 2)),
        sa.Column('channel',     sa.Text()),
        sa.Column('note',        sa.Text()),
    )
    op.create_table(
        'heizung_meters',
        sa.Column('id',                sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('apartment_id',      sa.Integer()),
        sa.Column('serial_number',     sa.Text()),
        sa.Column('description',       sa.Text()),
        sa.Column('unit_price',        sa.Numeric(10, 4), server_default='0.0'),
        sa.Column('unit_label',        sa.Text(), server_default='Einheiten'),
        sa.Column('conversion_factor', sa.Numeric(10, 4), server_default='1.0'),
    )
    op.create_table(
        'gas_meters',
        sa.Column('id',            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('apartment_id',  sa.Integer(), nullable=False),
        sa.Column('serial_number', sa.Text()),
        sa.Column('description',   sa.Text()),
        sa.Column('z_zahl',        sa.Numeric(10, 4), server_default='1.0'),
        sa.Column('brennwert',     sa.Numeric(10, 4), server_default='10.0'),
    )
    op.create_table(
        'co_tenants',
        sa.Column('id',          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('name',        sa.Text(),    nullable=False),
        sa.Column('gender',      sa.Text(),    server_default='diverse'),
        sa.Column('email',       sa.Text()),
        sa.Column('in_contract', sa.Integer(), server_default='0'),
    )
    op.create_table(
        'billing_profiles',
        sa.Column('id',           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id',    sa.Integer()),
        sa.Column('label',        sa.Text()),
        sa.Column('created_date', sa.Text()),
        sa.Column('data',         sa.Text()),
    )
    op.create_table(
        'config',
        sa.Column('key',   sa.Text(), primary_key=True),
        sa.Column('value', sa.Text()),
    )


def downgrade() -> None:
    for table in [
        'config', 'billing_profiles', 'co_tenants', 'gas_meters',
        'heizung_meters', 'reminders', 'flat_costs', 'payments',
        'contracts', 'tenants', 'apartments', 'properties',
    ]:
        op.drop_table(table)
