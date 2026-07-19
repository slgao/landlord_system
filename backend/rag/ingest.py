"""Load the markdown corpus and split it into retrieval chunks.

Chunking strategy: each corpus file is hand-curated so that every `## `
heading is already one semantically coherent unit (one Absatz / one
subsection). We chunk on those heading boundaries first — that respects the
document's own structure instead of cutting mid-sentence — and only fall
back to a token-based sliding window for the rare section that's still too
long for the embedding model's effective context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import tiktoken
import yaml

CORPUS_DIR = Path(__file__).parent / "corpus"

# Soft target size. e5-base-multilingual is happy well beyond this, but
# small chunks retrieve more precisely (less irrelevant text dragged along)
# at the cost of needing more of them to cover a topic. 350 tokens keeps one
# chunk to roughly one Absatz plus its "Praxisfolge" note.
CHUNK_SIZE_TOKENS = 350
CHUNK_OVERLAP_TOKENS = 50

_encoding = tiktoken.get_encoding("cl100k_base")  # approximation — see README


@dataclass
class Chunk:
    id: str
    text: str
    source_file: str
    section_title: str
    law_ref: str | None
    source_type: str  # "gesetz" | "internal_doc"
    url: str | None
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)

    def to_chroma_metadata(self) -> dict:
        return {
            "source_file": self.source_file,
            "section_title": self.section_title,
            "law_ref": self.law_ref or "",
            "source_type": self.source_type,
            "url": self.url or "",
            "chunk_index": self.chunk_index,
        }


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    _, fm, body = raw.split("---", 2)
    return yaml.safe_load(fm) or {}, body.strip()


def _split_by_heading(body: str) -> list[tuple[str, str]]:
    """Split on `## Heading` lines. Returns [(heading, section_text), ...]."""
    parts = re.split(r"^##\s+(.+)$", body, flags=re.MULTILINE)
    # parts[0] is any preamble before the first heading (usually empty)
    sections = []
    for i in range(1, len(parts), 2):
        heading, text = parts[i].strip(), parts[i + 1].strip()
        sections.append((heading, text))
    return sections


def _token_windows(text: str, size: int, overlap: int) -> list[str]:
    tokens = _encoding.encode(text)
    if len(tokens) <= size:
        return [text]
    windows, start = [], 0
    while start < len(tokens):
        window = tokens[start : start + size]
        windows.append(_encoding.decode(window))
        if start + size >= len(tokens):
            break
        start += size - overlap
    return windows


def load_corpus(corpus_dir: Path = CORPUS_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        for heading, section_text in _split_by_heading(body):
            windows = _token_windows(section_text, CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS)
            for idx, window in enumerate(windows):
                chunk_id = f"{path.stem}::{heading}::{idx}"
                chunks.append(
                    Chunk(
                        id=chunk_id,
                        text=f"{heading}\n\n{window}",
                        source_file=path.name,
                        section_title=heading,
                        law_ref=meta.get("law_ref"),
                        source_type=meta.get("source_type", "unknown"),
                        url=meta.get("url"),
                        chunk_index=idx,
                    )
                )
    return chunks


if __name__ == "__main__":
    cs = load_corpus()
    print(f"{len(cs)} chunks from {len(list(CORPUS_DIR.glob('*.md')))} files")
    for c in cs:
        print(f"  [{c.law_ref or c.source_type}] {c.id}  ({len(_encoding.encode(c.text))} tok)")
