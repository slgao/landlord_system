# Vermio RAG Assistant — architecture notes

`POST /api/rag/ask {"question": "..."}` — answers German landlord questions
(Betriebskosten, Kaution) grounded in real legal text (BetrKV, BGB §§551/556)
plus Vermio's own billing-logic docs, with per-claim citations and a refusal
path when the corpus doesn't cover the question.

Built as a practice project to get real, run-it-yourself RAG experience
(not just theory) before an AI Engineer interview whose team works on
LLM/RAG/Graph-RAG production systems on AWS Bedrock/SageMaker.

## Pipeline

```
question
  │
  ▼
HybridRetriever.retrieve()          dense (e5 embeddings via Chroma)
  │                                 + sparse (BM25)
  │                                 fused with Reciprocal Rank Fusion
  ▼
Reranker.rerank()                   cross-encoder scores (query, chunk)
  │                                 jointly — top_n=4 survive
  ▼
score < MIN_RERANK_SCORE? ──yes──▶  refuse, no LLM call
  │ no
  ▼
Generator.generate()                Groq (dev) / Bedrock Claude (prod-shaped)
  │                                 temperature=0, forced citations,
  │                                 explicit "say I don't know" instruction
  ▼
answer + citations + latency
```

Every stage is a swappable interface (`Embedder`, `Generator`) so the
Groq→Bedrock and local-embeddings→Titan swaps are one-line changes, not
rewrites — see `embed.py` / `generate.py`.

## Design decisions worth being able to defend out loud

**Chunking by heading, not fixed-size window.** The corpus is curated
markdown where every `## ` heading is already one Absatz. Chunking on that
boundary keeps each chunk semantically whole; a blind 300-token sliding
window would sometimes cut a legal sentence (and its citation) in half. Only
falls back to token windows (350 tok, 50 overlap) if a section is unusually
long. Trade-off: this only works because the corpus is small and hand-built
— at scale (thousands of ingested PDFs) you can't curate headings by hand,
so you'd lean on a layout-aware chunker (unstructured.io, or a
recursive-character splitter with paragraph/sentence boundaries as
fallback), and chunk size becomes a tuning knob you validate against the
eval set rather than assume.

**Hybrid retrieval (dense + BM25 + RRF), not dense-only.** Dense embeddings
miss exact tokens like "§551" or "12 Monate" — they get diluted into the
semantic average of the sentence. BM25 catches those verbatim. RRF (score =
Σ 1/(k+rank), k=60 per Cormack et al.) fuses both rankings without needing
to calibrate two different score scales against each other, which cosine
similarity vs. BM25's TF-IDF score can't be compared directly.

**Cross-encoder rerank as a second stage, not the primary retriever.**
Cross-encoders score (query, doc) jointly and are meaningfully more accurate
than bi-encoder cosine similarity — but that means one forward pass per
candidate, so it only runs on the ~16 fused candidates, never the full
corpus. This two-stage "retrieve cheap, rank precise" pattern is the same
shape as classic search-engine L1/L2 ranking.

**Refuse before generating, not just prompt-instructed refusal.** The system
prompt tells the model to say "I don't know" when context is insufficient —
but that's a soft instruction the model can ignore under pressure. The hard
guardrail is upstream: if the top reranked score is below
`MIN_RERANK_SCORE`, the pipeline never calls the LLM at all. Cheaper, and
doesn't depend on the model's instruction-following that day.

**Chroma over FAISS.** A few hundred chunks — raw ANN speed is irrelevant.
What matters here is metadata filtering (`source_type`, `law_ref`) without
hand-rolling an id→metadata sidecar. At real scale you'd move to
pgvector/OpenSearch or a managed vector store; Bedrock Knowledge Bases would
replace ingestion+embedding+storage+retrieval (stages 1–3 of the diagram
above) with a managed service entirely — worth being explicit in interview
that this repo is deliberately "build it yourself to understand the parts",
not an argument against using the managed path in production.

## What's NOT in this repo (and why that's a fine answer in interview)

- **Graph-RAG / knowledge graph.** The JD calls this out explicitly. This
  corpus (17 flat cost categories, a handful of BGB paragraphs) doesn't have
  enough *relational* structure to justify a graph over plain retrieval —
  forcing one in would be resume-driven-development, not a good engineering
  call. The honest answer in interview: "here's where a knowledge graph
  would earn its keep — modeling which of Europace's ~800 partner banks
  accept which borrower/property profile is genuinely graph-shaped (multi-hop:
  bank → accepted LTV range → property type → region), where flat retrieval
  would need one chunk per (bank, criterion) combination and still miss
  multi-hop questions like 'which banks accept self-employed applicants
  above 80% LTV in Bavaria' — a graph traversal answers that in one query,
  vector search over prose can't."
- **ragas-based evaluation.** `eval.py` hand-rolls hit-rate@k / MRR /
  refusal-accuracy to keep dependencies light for a few-day build. In
  production you'd use RAGAS (faithfulness, answer relevancy, context
  precision/recall) or a similar framework so eval numbers are comparable
  across projects and don't rot into home-grown metrics nobody else can
  interpret.
- **Query rewriting / HyDE / multi-query.** Worth mentioning as the next
  lever if hit-rate@k on the eval set were low — generate a
  hypothetical answer first and embed *that* (HyDE), or expand one query
  into several paraphrases and merge results. Skipped here because the
  eval set already hits well with the base hybrid pipeline; adding it
  without a measured gap would be premature.

## Running it

```bash
cd backend
pip install -r requirements.txt -r requirements-rag.txt
export GROQ_API_KEY=...        # console.groq.com, free tier

python -m rag.build_index --reset     # chunk + embed + index the corpus
python -m rag.ask "Wie hoch darf die Kaution maximal sein?"
python -m rag.eval                    # hit-rate@k, MRR, refusal accuracy
```

API: `uvicorn api.main:app --reload`, then
`curl -X POST localhost:8000/api/rag/ask -H 'content-type: application/json' -d '{"question": "..."}'`
(add `Authorization: Bearer <token>` if `APP_PASSWORD_HASH` is set).

## Bedrock swap (phase 2)

1. `embedder = BedrockEmbedder()` instead of `get_default_embedder()` in
   `pipeline.py` — re-run `build_index.py --reset` (dimension changes
   768→1024, index must be rebuilt, not incrementally updated).
2. `generator = BedrockGenerator()` instead of `GroqGenerator()` in
   `ask.py` / `routers/rag.py`.
3. Needs AWS credentials with `bedrock:InvokeModel` on
   `amazon.titan-embed-text-v2:0` and an enabled Claude model in the target
   region, plus model access requested in the Bedrock console (off by
   default per-account).
