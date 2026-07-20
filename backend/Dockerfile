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

# Pre-download the embedding + reranker models and build the legal index at
# build time, baking them into the image (HF_HOME). The assistant then answers
# legal questions instantly and offline — no ~1.5 GB download on the first
# request. This makes the image large (~3.5 GB) and needs network during
# `docker build`; HF_HUB_DOWNLOAD_TIMEOUT gives the large weight files headroom
# on a slow link. build_index needs no DB/API keys (corpus + embedder only).
#
# NOTE: because the weights live at /app/.hf_cache inside the image, do NOT
# mount a named volume there in docker-compose — an empty volume would shadow
# the baked models and force a runtime re-download.
ENV HF_HOME=/app/.hf_cache HF_HUB_DOWNLOAD_TIMEOUT=120
RUN python -m rag.build_index --reset \
    && python -c "from rag.retriever import Reranker; Reranker()"

RUN mkdir -p pdf

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
