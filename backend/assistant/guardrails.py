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
3. `require_scope` — a validity gate on the scope itself. The real isolation is
   the `owner_id = ?` predicate every tool query in tools.py now carries; this
   only rejects a missing or nonsensical scope so a tool can never run unscoped.
   `BOOTSTRAP_LANDLORD_ID` survives as the dev REPL's default owner, nothing more.
"""

from __future__ import annotations

# ── Cost / latency circuit-breakers (TRD §2, §8) ────────────────────────────
MAX_ITERATIONS = 6          # hard stop on the tool loop — cost + latency guard
# Groq has retired its Llama chat models. gpt-oss-120b is the strongest
# general model left on the platform and speaks the same OpenAI tool-calling
# shape, so the loop below needed no other change. It is a reasoning model,
# but Groq returns that on a separate `reasoning` field — never in `content`,
# so the streamed answer stays clean.
MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.0           # deterministic: this is a facts tool, not a writer
MAX_HISTORY_TURNS = 10      # bound replayed context (TRD §7)

# ── Default scope for the dev REPL (TRD §6, §11) ────────────────────────────
# Every owned table carries owner_id and every tool query filters on it, so
# isolation is enforced in SQL, not by this constant. It remains only as the
# owner assistant/repl.py runs as when driving the agent from a shell.
BOOTSTRAP_LANDLORD_ID = 1


class ScopeError(Exception):
    """Raised when a tool is asked to serve a landlord it is not scoped to.

    Surfaced to the model as a tool `{"error": ...}` (never as a crash), so an
    adversarial "show all tenants" prompt yields an empty/errored tool result
    rather than another landlord's rows.
    """


def require_scope(landlord_id: int) -> None:
    """Isolation gate. `landlord_id` is the authenticated owner id (verified by
    the auth layer); the real isolation is the `owner_id = ?` predicate every
    tool query now carries. We only reject a missing/invalid scope here so a tool
    can never run unscoped."""
    if not isinstance(landlord_id, int) or landlord_id <= 0:
        raise ScopeError(f"no data accessible for landlord {landlord_id} in this scope")


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
