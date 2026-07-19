"""Ties retrieval + rerank + generation into one call, plus the one guardrail
that matters most for a legal-ish Q&A tool: don't call the LLM at all on a
query the corpus clearly doesn't cover — a low similarity score is a much
cheaper and more reliable "I don't know" signal than trusting the prompt
instruction to stop the model from hallucinating.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .embed import Embedder, get_default_embedder
from .generate import Generator, GenerationResult
from .ingest import Chunk, load_corpus
from .retriever import HybridRetriever, Reranker, RetrievedChunk
from .vectorstore import VectorStore

# Below this fused RRF score, the reranker's cross-encoder score is the only
# thing we trust. Below MIN_RERANK_SCORE post-rerank, we refuse outright.
# Tuned by eye against the eval set in eval.py — not a principled constant.
MIN_RERANK_SCORE = 0.05

NO_CONTEXT_ANSWER = (
    "Dazu finde ich in meinen aktuellen Quellen (BetrKV, BGB §§551/556, "
    "Vermio-Doku) keine hinreichend sichere Antwort. Bitte im Zweifel "
    "anwaltlich prüfen lassen."
)


@dataclass
class AskResult:
    answer: str
    citations: list[dict]
    retrieved: list[RetrievedChunk]
    latency_ms: float
    refused: bool = False


class RagPipeline:
    def __init__(
        self,
        generator: Generator,
        embedder: Embedder | None = None,
        chunks: list[Chunk] | None = None,
        use_reranker: bool = True,
    ):
        self._embedder = embedder or get_default_embedder()
        self._chunks = chunks or load_corpus()
        self._store = VectorStore()
        if self._store.count() == 0:
            self._store.upsert(self._chunks, self._embedder)
        self._retriever = HybridRetriever(self._store, self._embedder, self._chunks)
        self._reranker = Reranker() if use_reranker else None
        self._generator = generator

    def ask(self, question: str, k: int = 8, top_n: int = 4) -> AskResult:
        import time

        t0 = time.perf_counter()
        candidates = self._retriever.retrieve(question, k=k)

        if self._reranker is not None:
            ranked = self._reranker.rerank(question, candidates, top_n=top_n)
        else:
            ranked = sorted(candidates, key=lambda c: c.score, reverse=True)[:top_n]

        # The threshold is calibrated for the reranker's sigmoid scores in
        # [0,1]. Without the reranker, scores are RRF sums (max ≈ 2/61 ≈
        # 0.033) — comparing those against 0.05 would refuse every query.
        low_confidence = self._reranker is not None and ranked and ranked[0].score < MIN_RERANK_SCORE
        if not ranked or low_confidence:
            return AskResult(
                answer=NO_CONTEXT_ANSWER, citations=[], retrieved=ranked,
                latency_ms=(time.perf_counter() - t0) * 1000, refused=True,
            )

        result: GenerationResult = self._generator.generate(question, [r.text for r in ranked])
        citations = [
            {"law_ref": r.metadata.get("law_ref") or r.metadata.get("source_file"),
             "section": r.metadata.get("section_title"), "score": round(r.score, 4)}
            for r in ranked
        ]
        return AskResult(
            answer=result.answer, citations=citations, retrieved=ranked,
            latency_ms=(time.perf_counter() - t0) * 1000, refused=False,
        )
