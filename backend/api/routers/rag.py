from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/rag", tags=["RAG Assistant"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Citation(BaseModel):
    law_ref: str | None
    section: str | None
    score: float


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation]
    latency_ms: float
    refused: bool


@lru_cache(maxsize=1)
def _get_pipeline():
    # Imported lazily so the main app can start without sentence-transformers
    # / chromadb / groq installed unless this endpoint is actually used —
    # those are pulled from requirements-rag.txt, not the base image.
    from rag.generate import GroqGenerator
    from rag.pipeline import RagPipeline

    return RagPipeline(generator=GroqGenerator())


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest) -> AskResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty")

    try:
        pipeline = _get_pipeline()
    except (ImportError, RuntimeError) as e:
        # Missing requirements-rag.txt deps or GROQ_API_KEY — a setup
        # problem, not a server crash. lru_cache doesn't cache the raised
        # exception, so this retries once the config is fixed.
        raise HTTPException(status_code=503, detail=f"RAG assistant not available: {e}")

    try:
        result = pipeline.ask(question)
    except Exception as e:
        # Upstream (Groq) failure: rate limit, network, model error.
        raise HTTPException(status_code=502, detail=f"Generation failed: {e}")

    return AskResponse(
        answer=result.answer,
        citations=[Citation(**c) for c in result.citations],
        latency_ms=result.latency_ms,
        refused=result.refused,
    )
