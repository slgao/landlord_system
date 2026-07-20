"""Guardrails for the agent loop (TRD §8).

Three jobs live here, all cheap and all load-bearing:

1. `sanitize_tool_output` — treat tool results as *data, not instructions*. A
   tenant's name or a contract note could contain "ignore previous instructions".
   We never let that text reach the model as anything but a `role:"tool"` payload,
   and we neutralise the most common injection markers so the model doesn't even
   see a fake instruction boundary.
2. Cost caps — `MAX_ITERATIONS` (the loop's circuit-breaker) and a per-request
   token budget live as constants the loop reads. Per-tenant daily quota (R9) is
   Phase 2 and hooks in at the router, not here.
3. `BOOTSTRAP_LANDLORD_ID` + `require_scope` — the single-tenant stand-in for the
   Phase-2 `landlord_id` predicate. Until the schema carries `landlord_id`
   (TRD §11), there is exactly one real landlord (id 1); a request scoped to any
   other id must see nothing. That gives us a *testable* isolation property today
   and a clean seam to swap for real RLS later.
"""

from __future__ import annotations

# ── Cost / latency circuit-breakers (TRD §2, §8) ────────────────────────────
MAX_ITERATIONS = 6          # hard stop on the tool loop — cost + latency guard
MODEL = "llama-3.3-70b-versatile"
TEMPERATURE = 0.0           # deterministic: this is a facts tool, not a writer
MAX_HISTORY_TURNS = 10      # bound replayed context (TRD §7)

# ── Single-tenant scope stand-in (TRD §6, §11) ──────────────────────────────
# Phase 1 has no `landlord_id` column yet, so tool SQL cannot say
# `WHERE landlord_id = ?`. Instead every tool asserts the scope is the one real
# landlord. Phase 2 deletes this guard and replaces it with the WHERE predicate +
# Postgres RLS. The important invariant — "a tool refuses to serve a foreign
# scope" — holds in both phases; only the mechanism changes.
BOOTSTRAP_LANDLORD_ID = 1


class ScopeError(Exception):
    """Raised when a tool is asked to serve a landlord it is not scoped to.

    Surfaced to the model as a tool `{"error": ...}` (never as a crash), so an
    adversarial "show all tenants" prompt yields an empty/errored tool result
    rather than another landlord's rows.
    """


def require_scope(landlord_id: int) -> None:
    """Phase-1 isolation gate. Any scope other than the bootstrap landlord is
    refused. Phase 2 replaces this with the SQL predicate + RLS session GUC."""
    if landlord_id != BOOTSTRAP_LANDLORD_ID:
        raise ScopeError(
            f"no data accessible for landlord {landlord_id} in this scope"
        )


# ── Prompt-injection neutralisation for tool payloads (TRD §8, R1-adjacent) ──
# We deliberately keep this conservative: we are not trying to "clean" data, only
# to strip the handful of tokens a model treats as a role/instruction boundary,
# so untrusted DB text can't forge one. The real defence is architectural (tool
# output only ever enters as a role:"tool" message, never the system prompt) —
# this is defence in depth on top of that.
_INJECTION_MARKERS = (
    "<|im_start|>", "<|im_end|>", "<|system|>", "<|user|>", "<|assistant|>",
    "###system", "###user", "###assistant",
)


def sanitize_tool_output(payload: str) -> str:
    """Neutralise instruction-boundary markers in a serialised tool result.

    `payload` is already JSON (see agent.py). We lower-case-match the markers so
    casing tricks don't slip through, and replace them with a visible, inert
    token so nothing is silently dropped.
    """
    cleaned = payload
    lowered = cleaned.lower()
    for marker in _INJECTION_MARKERS:
        idx = lowered.find(marker)
        while idx != -1:
            cleaned = cleaned[:idx] + "[removed]" + cleaned[idx + len(marker):]
            lowered = cleaned.lower()
            idx = lowered.find(marker)
    return cleaned
