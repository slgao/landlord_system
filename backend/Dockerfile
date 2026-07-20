FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Base app deps first — this layer is cached unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Assistant deps: groq (the agent loop's LLM client) + the legal-RAG stack
# (sentence-transformers, chromadb, rank-bm25). Without these the container's
# /api/assistant/ask and /api/rag/ask endpoints return 503.
#
# torch's default PyPI wheel bundles CUDA (~800 MB+): it bloats the image and
# its size makes the download timeout-prone on a slow link. We do inference on
# CPU, so install the CPU-only build from PyTorch's own index first, then the
# rest (torch is then already satisfied). The generous --timeout/--retries make
# the remaining large wheels resilient to flaky networks.
COPY requirements-rag.txt .
RUN pip install --no-cache-dir --timeout 300 --retries 5 \
        --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir --timeout 300 --retries 5 -r requirements-rag.txt

COPY . .

# Where Hugging Face caches the embedding + reranker weights. The legal tool
# downloads them (~1.5 GB) lazily on the FIRST legal question, then reuses this
# cache. Data tools (overdue rent, contracts, tax, …) need none of this and work
# immediately. To pre-bake the models + index at build time instead (bigger
# image, but no first-request download and works offline), add:
#     RUN python -m rag.build_index --reset \
#         && python -c "from rag.retriever import Reranker; Reranker()"
ENV HF_HOME=/app/.hf_cache

RUN mkdir -p pdf

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
