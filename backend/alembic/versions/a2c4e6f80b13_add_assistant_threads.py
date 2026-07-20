"""add assistant conversation persistence

Revision ID: a2c4e6f80b13
Revises: f1b2c3d4e5f6
Create Date: 2026-07-20

Backing store for the Ask Vermio assistant's multi-turn conversations
(docs/TRD-assistant.md §7). Two tables:

  assistant_threads   — one row per conversation, scoped by landlord_id.
  assistant_messages  — the turns; role in {user, assistant, tool}.

landlord_id is present from day one even though the rest of the schema is still
single-tenant (Phase 1): the assistant is designed multi-tenant from the start,
so this column is a fill-in for Phase 2, not a later migration. No FK to a
`landlords` table yet — that table arrives with the Phase-2 multi-tenancy
migration (TRD §11); until then every row carries the bootstrap landlord id 1.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a2c4e6f80b13'
down_revision: Union[str, Sequence[str], None] = 'f1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'assistant_threads',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('landlord_id', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=True),
    )
    op.create_index('ix_assistant_threads_landlord', 'assistant_threads', ['landlord_id'])

    op.create_table(
        'assistant_messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('thread_id', sa.Integer(),
                  sa.ForeignKey('assistant_threads.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('role', sa.Text(), nullable=False),       # user | assistant | tool
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('tool_calls', sa.Text(), nullable=True),  # JSON, null for plain messages
        sa.Column('created_at', sa.Text(), nullable=True),
    )
    op.create_index('ix_assistant_messages_thread', 'assistant_messages', ['thread_id'])


def downgrade() -> None:
    op.drop_index('ix_assistant_messages_thread', table_name='assistant_messages')
    op.drop_table('assistant_messages')
    op.drop_index('ix_assistant_threads_landlord', table_name='assistant_threads')
    op.drop_table('assistant_threads')
