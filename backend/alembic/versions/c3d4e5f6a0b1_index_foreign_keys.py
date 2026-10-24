"""Index the foreign keys every report joins over

Revision ID: c3d4e5f6a0b1
Revises: b2c3d4e5f8a9
Create Date: 2026-10-24

Fourteen foreign keys had no index, among them `payments.contract_id` — the
column the arrears query joins on, which is the slowest query in the app.

Measured on a database holding sixty landlords, 720 contracts and five years of
rent (43.200 payments), the query behind both the Payment Reminders page and
the dashboard's cashflow card:

    Seq Scan on payments  (rows=43200)  67 ms    ← before
    Nested Loop via index (rows=720)   2.2 ms    ← after
    whole query                        89 → 4.6 ms
    /api/reports/payment-reminders     42 → 24 ms
    /api/insights/flats                49 → 24 ms

The shape of that number matters more than its size. Without the index the
cost is set by how many payments *every* landlord has entered, because one
owner's arrears query reads the whole table to throw almost all of it away;
with it, the cost is set by that owner's own contracts. The first grows with
the deployment, the second does not.

An unindexed foreign key also makes the parent's DELETE scan the child whole
to check the constraint — deleting a property had to read every payment row.

`owner_id` is already indexed on every table, but it is the wrong column to
lean on: in a multi-tenant database it is the *least* selective one, since a
single owner holds most of their own rows. The selective column is the key.
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'c3d4e5f6a0b1'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (index name, table, column). Every foreign key in the schema that had no
# index with it as the leading column — the only position a join can use.
# strom_meters and wasser_meters are absent because they were indexed when
# they were added; gas and heizung were not, which is how this was noticed.
FK_INDEXES = [
    ("ix_payments_contract_id",          "payments",          "contract_id"),
    ("ix_apartments_property_id",        "apartments",        "property_id"),
    ("ix_contracts_apartment_id",        "contracts",         "apartment_id"),
    ("ix_contracts_tenant_id",           "contracts",         "tenant_id"),
    ("ix_flat_costs_apartment_id",       "flat_costs",        "apartment_id"),
    ("ix_expenses_property_id",          "expenses",          "property_id"),
    ("ix_expenses_apartment_id",         "expenses",          "apartment_id"),
    ("ix_mortgages_property_id",         "mortgages",         "property_id"),
    ("ix_co_tenants_contract_id",        "co_tenants",        "contract_id"),
    ("ix_reminders_contract_id",         "reminders",         "contract_id"),
    ("ix_billing_profiles_tenant_id",    "billing_profiles",  "tenant_id"),
    ("ix_gas_meters_apartment_id",       "gas_meters",        "apartment_id"),
    ("ix_heizung_meters_apartment_id",   "heizung_meters",    "apartment_id"),
    ("ix_properties_building_id",        "properties",        "building_id"),
]


def upgrade() -> None:
    for name, table, column in FK_INDEXES:
        # IF NOT EXISTS because a deployment may already have been indexed by
        # hand; the migration has to be safe to run against it either way.
        op.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{column}")')


def downgrade() -> None:
    for name, _table, _column in FK_INDEXES:
        op.execute(f'DROP INDEX IF EXISTS "{name}"')
