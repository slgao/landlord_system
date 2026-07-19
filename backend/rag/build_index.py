"""One-off / re-run-on-corpus-change CLI: chunk the corpus and (re)populate
the Chroma index. Run this after editing anything under corpus/.

    python -m rag.build_index [--reset]
"""

from __future__ import annotations

import argparse

from .embed import get_default_embedder
from .ingest import load_corpus
from .vectorstore import VectorStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop and rebuild the collection")
    args = parser.parse_args()

    chunks = load_corpus()
    embedder = get_default_embedder()
    store = VectorStore()
    if args.reset:
        store.reset()
    store.upsert(chunks, embedder)
    print(f"Indexed {len(chunks)} chunks into '{store._collection.name}' "
          f"(collection now has {store.count()} vectors)")


if __name__ == "__main__":
    main()
