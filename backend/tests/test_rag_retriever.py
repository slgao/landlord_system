"""Tests for rag.retriever — BM25 tokenization and hybrid RRF fusion.

Uses stub store/embedder objects so no models, network, or Chroma index are
needed. Skipped entirely when the optional RAG deps (requirements-rag.txt)
aren't installed, so the core suite stays runnable without them.
"""
import pytest

pytest.importorskip("rank_bm25")
pytest.importorskip("tiktoken")
pytest.importorskip("chromadb")

from rag.ingest import Chunk
from rag.retriever import HybridRetriever, _tokenize


def _chunk(cid, text):
    return Chunk(id=cid, text=text, source_file="f.md", section_title="s",
                 law_ref=None, source_type="internal_doc", url=None)


class _FakeStore:
    """Returns a canned dense ranking; mimics VectorStore.query's dict shape."""

    def __init__(self, ranked):
        self._ranked = ranked  # [(chunk_id, score), ...] best first

    def query(self, query_vector, k=10, where=None):
        return [{"id": cid, "text": "", "metadata": {}, "score": s}
                for cid, s in self._ranked[:k]]


class _FakeEmbedder:
    def embed_query(self, text):
        return [0.0]

    def embed_documents(self, texts):
        return [[0.0] for _ in texts]


def test_tokenize_strips_punctuation():
    # "§551," in the corpus must match a query for "§551" — the whole point
    # of having BM25 in the hybrid is exact legal-token matching.
    assert _tokenize("Die Kaution (§551,) ist fällig.") == ["die", "kaution", "551", "ist", "fällig"]
    assert _tokenize("§551") == ["551"]


def test_dense_ids_used_verbatim():
    # Regression: ids from the vector store must be used as-is, not
    # reconstructed from metadata (ids here deliberately don't follow the
    # file::section::index scheme).
    chunks = [_chunk("weird-id-1", "kaution höhe"), _chunk("weird-id-2", "heizkosten")]
    store = _FakeStore([("weird-id-1", 0.9), ("weird-id-2", 0.5)])
    retr = HybridRetriever(store, _FakeEmbedder(), chunks)
    results = retr.retrieve("kaution", k=2)
    assert [r.text for r in results]  # non-empty: ids resolved to chunks
    assert results[0].text == "kaution höhe"


def test_rrf_fuses_dense_and_sparse():
    # Chunk A wins on BM25 (exact token), chunk B wins on dense; a chunk
    # ranked well by BOTH should beat one ranked well by only one signal.
    chunks = [
        _chunk("a", "die kaution beträgt drei monatsmieten §551"),
        _chunk("b", "betriebskosten sind kosten des gebäudes"),
        _chunk("c", "kaution und betriebskosten im überblick"),
    ]
    # Dense ranking favors c then b; BM25 for the query below favors a and c.
    store = _FakeStore([("c", 0.9), ("b", 0.8), ("a", 0.1)])
    retr = HybridRetriever(store, _FakeEmbedder(), chunks)
    results = retr.retrieve("kaution §551", k=3)
    ids_in_order = [r.metadata["source_file"] and r.text for r in results]
    # c appears in both rankings' top → highest fused score.
    assert results[0].text == "kaution und betriebskosten im überblick"
    # All three still present (k=3).
    assert len(results) == 3


def test_unknown_dense_id_skipped():
    # A stale index entry (id not in the loaded corpus) must be skipped, not crash.
    chunks = [_chunk("a", "kaution")]
    store = _FakeStore([("ghost", 0.9), ("a", 0.5)])
    retr = HybridRetriever(store, _FakeEmbedder(), chunks)
    results = retr.retrieve("kaution", k=2)
    assert [r.text for r in results] == ["kaution"]
