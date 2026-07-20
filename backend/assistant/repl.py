"""Scratch driver for the agent — TRD §12 Step 2/3, "hand-run the tool loop".

Runs `run_agent` against the real dev database + Groq, printing the tool trace so
you can *see* the model decide what to call. This is the single most clarifying
exercise for understanding the whole system.

Usage (from the repo root, so the .env is found):

    # one-shot
    venv/bin/python -m assistant.repl "Welche Mieter sind überfällig?"
    PYTHONPATH=backend venv/bin/python -m assistant.repl "..."   # if run elsewhere

    # interactive multi-turn (history is kept across questions)
    venv/bin/python -m assistant.repl

    # show the full message transcript (tool args + raw results)
    venv/bin/python -m assistant.repl -v "Wie hoch ist die Kaution für Wohnung 1?"

Requires GROQ_API_KEY and DATABASE_URL — both loaded from the repo-root .env
below, *before* anything imports db.py (which reads DATABASE_URL at import time).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ── Load env BEFORE importing anything that touches the DB ───────────────────
# db.py does `os.environ["DATABASE_URL"]` at import time, so the .env has to be
# in the environment first. Look for it at the repo root (two levels up).
try:
    from dotenv import load_dotenv

    for candidate in (Path.cwd() / ".env",
                      Path(__file__).resolve().parents[2] / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            break
except ImportError:
    pass  # rely on the ambient environment (e.g. run under honcho)

# Make `backend/` importable when invoked as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assistant.agent import run_agent          # noqa: E402
from assistant.guardrails import BOOTSTRAP_LANDLORD_ID  # noqa: E402

LANDLORD_ID = BOOTSTRAP_LANDLORD_ID

# ANSI dim/bold — harmless if the terminal ignores them.
_DIM, _BOLD, _RST = "\033[2m", "\033[1m", "\033[0m"


def _preflight() -> None:
    missing = [k for k in ("GROQ_API_KEY", "DATABASE_URL") if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)} — run from the repo root so .env loads")


def _print_transcript(messages: list[dict]) -> None:
    """Dump the tool round-trips (what the model asked for, what it got back)."""
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                fn = tc["function"]
                print(f"{_DIM}  → call {fn['name']}({fn.get('arguments', '')}){_RST}")
        elif role == "tool":
            body = m.get("content", "")
            snippet = body if len(body) < 500 else body[:500] + "…"
            print(f"{_DIM}  ← {snippet}{_RST}")


def ask(question: str, history: list[dict], verbose: bool) -> str:
    result = run_agent(question, landlord_id=LANDLORD_ID, history=history)
    tools = result["tools_consulted"]
    if tools:
        print(f"{_DIM}tools consulted: {', '.join(tools)}{_RST}")
    if verbose:
        _print_transcript(result["messages"])
    print(f"\n{_BOLD}{result['answer']}{_RST}\n")
    return result["answer"]


def main() -> None:
    args = [a for a in sys.argv[1:] if a not in ("-v", "--verbose")]
    verbose = any(a in ("-v", "--verbose") for a in sys.argv[1:])
    _preflight()

    history: list[dict] = []

    if args:  # one-shot
        q = " ".join(args)
        print(f"{_BOLD}> {q}{_RST}")
        ask(q, history, verbose)
        return

    # interactive
    print("Ask Vermio REPL — landlord_id=%d. Ctrl-D / 'exit' to quit.\n" % LANDLORD_ID)
    while True:
        try:
            q = input(f"{_BOLD}> {_RST}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q or q in ("exit", "quit"):
            break
        answer = ask(q, history, verbose)
        # Keep a rolling plain user/assistant history so follow-ups have context.
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
        history = history[-20:]  # bound to ~10 turns (TRD §7)


if __name__ == "__main__":
    main()
