"""add foreign key constraints

Revision ID: b9e7f2a4c8d6
Revises: a8d4f6c19b53
Create Date: 2026-05-02

Adds the FK constraints that were never declared at table-creation time.

Cascade strategy:
- RESTRICT on the relationships that protect history (you must clear the
  child rows manually before deleting the parent):
    apartments.property_id  → properties.id
    contracts.tenant_id     → tenants.id
    contracts.apartment_id  → apartments.id
- CASCADE on per-contract / per-apartment / per-tenant detail rows
  (payments, kaution deductions, flat costs, meters, reminders,
  co-tenants, billing profiles).

meter_readings has a polymorphic (meter_type, meter_id) reference and
cannot have a regular FK; left as-is (item 1f from the code review).
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'b9e7f2a4c8d6'
down_revision: Union[str, Sequence[str], None] = 'a8d4f6c19b53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_RESTRICT = [
    ("fk_apartments_property",     "apartments",  "property_id",  "properties",  "id"),
    ("fk_contracts_tenant",        "contracts",   "tenant_id",    "tenants",     "id"),
    ("fk_contracts_apartment",     "contracts",   "apartment_id", "apartments",  "id"),
]

_CASCADE = [
    ("fk_payments_contract",          "payments",          "contract_id",  "contracts",  "id"),
    ("fk_kaution_deductions_contract","kaution_deductions","contract_id",  "contracts",  "id"),
    ("fk_flat_costs_apartment",       "flat_costs",        "apartment_id", "apartments", "id"),
    ("fk_reminders_contract",         "reminders",         "contract_id",  "contracts",  "id"),
    ("fk_co_tenants_contract",        "co_tenants",        "contract_id",  "contracts",  "id"),
    ("fk_billing_profiles_tenant",    "billing_profiles",  "tenant_id",    "tenants",    "id"),
    ("fk_heizung_meters_apartment",   "heizung_meters",    "apartment_id", "apartments", "id"),
    ("fk_gas_meters_apartment",       "gas_meters",        "apartment_id", "apartments", "id"),
    ("fk_strom_meters_apartment",     "strom_meters",      "apartment_id", "apartments", "id"),
    ("fk_wasser_meters_apartment",    "wasser_meters",     "apartment_id", "apartments", "id"),
]


def upgrade() -> None:
    for name, table, col, ref_table, ref_col in _RESTRICT:
        op.create_foreign_key(name, table, ref_table, [col], [ref_col], ondelete="RESTRICT")
    for name, table, col, ref_table, ref_col in _CASCADE:
        op.create_foreign_key(name, table, ref_table, [col], [ref_col], ondelete="CASCADE")


def downgrade() -> None:
    for name, table, *_ in _RESTRICT + _CASCADE:
        op.drop_constraint(name, table, type_="foreignkey")
