"""Manual smoke-test CLI.

    python -m rag.ask "Wie hoch darf die Kaution maximal sein?"
    python -m rag.ask   # interactive loop
"""

from __future__ import annotations

import sys

from .generate import GroqGenerator
from .pipeline import RagPipeline


def main() -> None:
    pipeline = RagPipeline(generator=GroqGenerator())

    if len(sys.argv) > 1:
        questions = [" ".join(sys.argv[1:])]
    else:
        questions = iter(lambda: input("\n> "), "")

    for q in questions:
        result = pipeline.ask(q)
        print(f"\n{result.answer}\n")
        print(f"[{result.latency_ms:.0f}ms, refused={result.refused}]")
        for c in result.citations:
            print(f"  - {c['law_ref']} / {c['section']}  (score={c['score']})")


if __name__ == "__main__":
    main()
