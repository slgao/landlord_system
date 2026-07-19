"""Hybrid retrieval: dense (embeddings) + sparse (BM25), fused with
Reciprocal Rank Fusion, then optionally re-ranked with a cross-encoder.

Why hybrid at all for a corpus this small: dense retrieval is good at
semantic paraphrase ("wie viel darf die Kaution sein" ~ "Höchstgrenze der
Mietsicherheit") but weak on exact legal citations and numbers ("§551",
"12 Monate", "Nr. 14") because those tokens get diluted in the embedding.
BM25 is the opposite — exact lexical/number matches, weak on paraphrase.
Fusing both is cheap insurance against either failure mode, and it's a
standard production pattern (Bedrock Knowledge Bases, Elastic, Vespa all
default to hybrid now), not something exotic in this demo only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from .embed import Embedder
from .ingest import Chunk
from .vectorstore import VectorStore


@dataclass
class RetrievedChunk:
    text: str
    metadata: dict
    score: float


def _tokenize(text: str) -> list[str]:
    # \w+ (unicode-aware) instead of split(): a plain split leaves punctuation
    # glued to tokens ("§551," ≠ "§551"), which silently kills the exact
    # legal-token matching BM25 exists to provide here.
    return re.findall(r"\w+", text.lower())


class HybridRetriever:
    def __init__(self, store: VectorStore, embedder: Embedder, chunks: list[Chunk]):
        self._store = store
        self._embedder = embedder
        self._chunks = {c.id: c for c in chunks}
        corpus_tokens = [_tokenize(c.text) for c in chunks]
        self._bm25 = BM25Okapi(corpus_tokens)
        self._bm25_ids = [c.id for c in chunks]

    def _dense(self, query: str, k: int) -> list[tuple[str, float]]:
        qvec = self._embedder.embed_query(query)
        hits = self._store.query(qvec, k=k)
        return [(h["id"], h["score"]) for h in hits]

    def _sparse(self, query: str, k: int) -> list[tuple[str, float]]:
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self._bm25_ids, scores), key=lambda x: x[1], reverse=True)
        return ranked[:k]

    def retrieve(self, query: str, k: int = 8, rrf_k: int = 60) -> list[RetrievedChunk]:
        """Reciprocal Rank Fusion: score = sum(1 / (rrf_k + rank)) across
        both rankings. rrf_k=60 is the value from the original Cormack et
        al. RRF paper and is a reasonable default without needing to tune it
        per-corpus."""
        dense_ranked = self._dense(query, k=k * 2)
        sparse_ranked = self._sparse(query, k=k * 2)

        fused: dict[str, float] = {}
        for rank, (cid, _) in enumerate(dense_ranked):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)
        for rank, (cid, _) in enumerate(sparse_ranked):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (rrf_k + rank + 1)

        top_ids = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:k]
        results = []
        for cid, score in top_ids:
            chunk = self._chunks.get(cid)
            if chunk is None:
                continue
            results.append(RetrievedChunk(text=chunk.text, metadata=chunk.to_chroma_metadata(), score=score))
        return results


class Reranker:
    """Cross-encoder re-rank of the fused candidate set. A cross-encoder
    scores (query, chunk) jointly instead of comparing two independently
    computed vectors — much more accurate at judging relevance, but O(k)
    forward passes instead of one, so it only runs on the small fused
    shortlist, never on the whole corpus."""

    def __init__(self, model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"):
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[RetrievedChunk], top_n: int = 4) -> list[RetrievedChunk]:
        if not candidates:
            return []
        import torch

        pairs = [(query, c.text) for c in candidates]
        # Raw output of this model is an unbounded regression logit, not a
        # [0,1] relevance score — has to go through a sigmoid before it's
        # meaningful to threshold against (see MIN_RERANK_SCORE in
        # pipeline.py). Easy to skip this and get a threshold that's
        # calibrated against nothing.
        scores = self._model.predict(pairs, activation_fn=torch.nn.Sigmoid())
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [RetrievedChunk(text=c.text, metadata=c.metadata, score=float(s)) for c, s in ranked[:top_n]]
