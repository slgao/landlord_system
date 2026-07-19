"""Thin wrapper around a persistent Chroma collection.

Chroma over FAISS here on purpose: this corpus is a few hundred chunks, not
millions, so raw ANN throughput doesn't matter — what matters for a fast
build is metadata filtering (by source_type, law_ref) and not having to
hand-roll an ID<->metadata sidecar file, which is what plain FAISS makes you
do. At real scale (millions of vectors, need for HNSW tuning, sharding)
you'd reach for something like OpenSearch/pgvector/a managed vector DB, or
exactly the managed path Bedrock Knowledge Bases offers — see README.
"""

from __future__ import annotations

from pathlib import Path

import chromadb

from .embed import Embedder
from .ingest import Chunk

PERSIST_DIR = Path(__file__).parent / ".chroma"
COLLECTION_NAME = "vermio_legal"


class VectorStore:
    def __init__(self, persist_dir: Path = PERSIST_DIR, collection_name: str = COLLECTION_NAME):
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

    def reset(self) -> None:
        self._client.delete_collection(self._collection.name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection.name, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, chunks: list[Chunk], embedder: Embedder) -> None:
        vectors = embedder.embed_documents([c.text for c in chunks])
        self._collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[c.to_chroma_metadata() for c in chunks],
        )

    def query(self, query_vector: list[float], k: int = 10, where: dict | None = None) -> list[dict]:
        res = self._collection.query(
            query_embeddings=[query_vector], n_results=k, where=where,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for cid, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            out.append({"id": cid, "text": doc, "metadata": meta, "score": 1 - dist})  # cosine distance -> similarity
        return out

    def count(self) -> int:
        return self._collection.count()
