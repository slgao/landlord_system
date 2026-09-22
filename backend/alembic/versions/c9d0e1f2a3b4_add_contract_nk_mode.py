"""add contracts.nk_mode

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-22

How a contract charges Nebenkosten, which decides whether a yearly
Nebenkostenabrechnung is owed at all:

- 'prepayment' — Vorauszahlungen, settled against the real costs once a
  year. §556 Abs. 3 BGB applies: the Abrechnung is due within twelve
  months of the period's end.
- 'flat' — a Pauschale (or a Warmmiete that includes the Nebenkosten).
  Nothing is settled, so there is no Abrechnung and no deadline.

nebenkosten_vorauszahlung keeps its meaning in both — the utilities part of
the rent — because the Kaltmiete/Umlagen split and every €/m² figure need
it either way. Existing contracts default to 'prepayment', which is what
the app assumed until now.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contracts', sa.Column('nk_mode', sa.Text(), nullable=False,
                                         server_default='prepayment'))
    op.create_check_constraint('ck_contracts_nk_mode', 'contracts',
                               "nk_mode IN ('prepayment', 'flat')")


def downgrade() -> None:
    op.drop_constraint('ck_contracts_nk_mode', 'contracts', type_='check')
    op.drop_column('contracts', 'nk_mode')
