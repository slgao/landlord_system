"""Conversation persistence (TRD §7).

Two tables (created by the alembic migration `..._add_assistant_threads`):

    assistant_threads(id, landlord_id, title, created_at)
    assistant_messages(id, thread_id, role, content, tool_calls, created_at)

Multi-turn context (R4) = replay a thread's prior user/assistant messages into
the agent's `history`. Everything here is scoped by `landlord_id` via the thread,
so a landlord can only ever load their own conversations — the same isolation
rule as the data tools, applied to chat history.

We persist only the *plain* user and assistant messages, not the intra-turn tool
round-trips: the final answers carry the context the next turn needs, and keeping
history small bounds token cost. The `tool_calls` column is reserved for when we
want to replay full tool transcripts (Phase 2).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import db
from .guardrails import MAX_HISTORY_TURNS

# Roles we replay into the model's context. Tool messages are ephemeral.
_HISTORY_ROLES = ("user", "assistant")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_returning_id(sql: str, params: tuple) -> int:
    """INSERT ... RETURNING id in one committed round-trip.

    db.insert() assumes a positional VALUES tuple and returns nothing; db.execute
    commits but discards rows; db.fetch returns rows but doesn't commit. We need
    commit *and* the new id, so we drive a pooled connection directly (same
    borrow/return discipline as db.py)."""
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        new_id = cur.fetchone()[0]
        conn.commit()
        return int(new_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        db.put_conn(conn)


def create_thread(landlord_id: int, title: str | None = None) -> int:
    return _insert_returning_id(
        """INSERT INTO assistant_threads (landlord_id, title, created_at)
           VALUES (%s, %s, %s) RETURNING id""",
        (landlord_id, title, _now()),
    )


def thread_belongs_to(landlord_id: int, thread_id: int) -> bool:
    """Isolation check: is this thread owned by this landlord? Every thread
    access goes through here so history can never cross tenants."""
    rows = db.fetch(
        "SELECT 1 FROM assistant_threads WHERE id = ? AND landlord_id = ?",
        (thread_id, landlord_id),
    )
    return bool(rows)


def list_threads(landlord_id: int) -> list[dict]:
    rows = db.fetch(
        """SELECT id, title, created_at FROM assistant_threads
           WHERE landlord_id = ? ORDER BY id DESC""",
        (landlord_id,),
    )
    return [{"thread_id": tid, "title": title, "created_at": ts} for tid, title, ts in rows]


def append_message(thread_id: int, role: str, content: str,
                   tool_calls: list | None = None) -> None:
    db.execute(
        """INSERT INTO assistant_messages (thread_id, role, content, tool_calls, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (thread_id, role, content,
         json.dumps(tool_calls) if tool_calls else None, _now()),
    )


def load_history(landlord_id: int, thread_id: int,
                 max_turns: int = MAX_HISTORY_TURNS) -> list[dict]:
    """Return the last ~max_turns user/assistant messages as OpenAI-format
    dicts, oldest first. Returns [] for a thread the landlord doesn't own."""
    if not thread_belongs_to(landlord_id, thread_id):
        return []
    # 2 messages per turn (user + assistant); fetch newest, then reverse.
    rows = db.fetch(
        """SELECT role, content FROM assistant_messages
           WHERE thread_id = ? AND role IN ('user', 'assistant')
           ORDER BY id DESC LIMIT ?""",
        (thread_id, max_turns * 2),
    )
    return [{"role": role, "content": content} for role, content in reversed(rows)]
