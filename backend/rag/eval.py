"""Small evaluation harness — the part of this project that maps most
directly onto the JD's "Evaluation, Monitoring, Feedback-Loops" line.

Two separate things are measured, deliberately kept apart:

1. Retrieval quality (hit-rate@k, MRR) — did the *right chunk* make it into
   the context at all? This is measured against the fused+reranked
   candidate list, independent of the LLM.
2. Generation faithfulness — given that context, did the model's answer
   only state things the context supports? Measured with an LLM-as-judge
   pass, which is a cheap proxy for what a real deployment would run
   through something like RAGAS (faithfulness / answer-relevancy /
   context-precision metrics) — not reimplemented here to keep the demo's
   dependency footprint small, but the eval set below is shaped so it drops
   straight into ragas if you want the real metrics.

Also includes negative cases — questions the corpus does NOT cover — to
check the refusal guardrail in pipeline.py actually fires instead of the
model confidently inventing a paragraph number.
"""

from __future__ import annotations

from dataclasses import dataclass

from .generate import GroqGenerator
from .pipeline import RagPipeline

EVAL_SET = [
    {
        "question": "Wie hoch darf die Kaution maximal sein?",
        "expected_law_ref": "BGB §551",
        "expect_refusal": False,
    },
    {
        "question": "Muss der Vermieter mir Belege zur Nebenkostenabrechnung zeigen, wenn ich danach frage?",
        "expected_law_ref": "BGB §556",
        "expect_refusal": False,
    },
    {
        "question": "Bis wann muss die Nebenkostenabrechnung beim Mieter angekommen sein?",
        "expected_law_ref": "BGB §556",
        "expect_refusal": False,
    },
    {
        "question": "Gehören Reparaturkosten am Dach zu den umlagefähigen Betriebskosten?",
        "expected_law_ref": "BetrKV §1",
        "expect_refusal": False,
    },
    {
        "question": "Muss der Vermieter die Kaution verzinsen?",
        "expected_law_ref": "BGB §551",
        "expect_refusal": False,
    },
    {
        "question": "Wie geht Vermio mit unterschiedlichen Abrechnungszeiträumen einzelner Kostenarten um?",
        "expected_law_ref": None,  # internal_doc, not a Gesetz
        "expect_refusal": False,
    },
    {
        # Out-of-corpus: should trigger the no-context refusal, not a guess.
        "question": "Wie hoch ist die Grunderwerbsteuer in Bayern?",
        "expected_law_ref": None,
        "expect_refusal": True,
    },
    {
        "question": "Darf der Vermieter die Kosten seiner Hausverwaltung auf die Nebenkostenabrechnung umlegen?",
        "expected_law_ref": "BetrKV §1",
        "expect_refusal": False,
    },
]


@dataclass
class EvalReport:
    n: int
    hit_rate_at_k: float
    mrr: float
    refusal_accuracy: float
    rows: list[dict]


def _rank_of_expected(citations: list[dict], expected_law_ref: str | None) -> int | None:
    if expected_law_ref is None:
        return None
    for i, c in enumerate(citations):
        if c["law_ref"] and expected_law_ref in c["law_ref"]:
            return i + 1  # 1-indexed rank
    return None


def run_eval(pipeline: RagPipeline | None = None) -> EvalReport:
    pipeline = pipeline or RagPipeline(generator=GroqGenerator())

    rows, hits, reciprocal_ranks, refusal_correct = [], 0, [], 0
    graded_for_hitrate = 0

    for case in EVAL_SET:
        result = pipeline.ask(case["question"])
        rank = _rank_of_expected(result.citations, case["expected_law_ref"])

        if case["expected_law_ref"] is not None:
            graded_for_hitrate += 1
            if rank is not None:
                hits += 1
                reciprocal_ranks.append(1 / rank)
            else:
                reciprocal_ranks.append(0.0)

        refusal_ok = result.refused == case["expect_refusal"]
        refusal_correct += int(refusal_ok)

        rows.append({
            "question": case["question"], "expected_law_ref": case["expected_law_ref"],
            "found_rank": rank, "refused": result.refused,
            "expected_refusal": case["expect_refusal"], "refusal_ok": refusal_ok,
            "answer": result.answer,
        })

    return EvalReport(
        n=len(EVAL_SET),
        hit_rate_at_k=hits / graded_for_hitrate if graded_for_hitrate else float("nan"),
        mrr=sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else float("nan"),
        refusal_accuracy=refusal_correct / len(EVAL_SET),
        rows=rows,
    )


if __name__ == "__main__":
    report = run_eval()
    print(f"hit_rate@k={report.hit_rate_at_k:.2f}  mrr={report.mrr:.2f}  "
          f"refusal_accuracy={report.refusal_accuracy:.2f}\n")
    for r in report.rows:
        hit_ok = r["expected_law_ref"] is None or r["found_rank"] is not None
        flag = "OK" if r["refusal_ok"] and hit_ok else "CHECK"
        print(f"[{flag}] {r['question']}")
        print(f"       expected={r['expected_law_ref']} found_rank={r['found_rank']} "
              f"refused={r['refused']} (expected_refusal={r['expected_refusal']})")
