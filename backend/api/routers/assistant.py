"""POST /api/assistant/ask — the Ask Vermio endpoint (TRD Step 5, §13).

Non-streaming first (simpler to debug); streaming is TRD Step 6 and slots in
behind the same request contract. The endpoint's one security job is to derive
`landlord_id` from the *verified identity*, never from the request body, and hand
it to the agent — everything downstream trusts that value.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import require_auth
from assistant.agent import run_agent, run_agent_stream
from assistant.guardrails import BOOTSTRAP_LANDLORD_ID
from assistant import threads

router = APIRouter(prefix="/assistant", tags=["Assistant"])


def resolve_landlord_id(user: str) -> int:
    """The single source of `landlord_id` (TRD §6, §11).

    Phase 1 is single-tenant, so every authenticated user maps to the one
    bootstrap landlord. Phase 2 replaces this with a JWT custom claim
    (`landlord_id`) read off the verified token — the *only* change needed here,
    because nothing else in the stack sources the scope from anywhere else.
    """
    return BOOTSTRAP_LANDLORD_ID


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    thread_id: int | None = Field(default=None,
                                  description="Continue an existing conversation; "
                                              "omit to start a new one.")


class AskResponse(BaseModel):
    answer: str
    tools_consulted: list[str]
    thread_id: int


class ThreadSummary(BaseModel):
    thread_id: int
    title: str | None
    created_at: str | None


@router.get("/threads", response_model=list[ThreadSummary])
def list_threads(user: str = Depends(require_auth)) -> list[ThreadSummary]:
    landlord_id = resolve_landlord_id(user)
    return [ThreadSummary(**t) for t in threads.list_threads(landlord_id)]


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, user: str = Depends(require_auth)) -> AskResponse:
    landlord_id = resolve_landlord_id(user)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty")

    # Resolve the thread — creating one on first message, and refusing any thread
    # that isn't this landlord's (isolation applies to history too).
    if body.thread_id is None:
        thread_id = threads.create_thread(landlord_id, title=question[:80])
        history: list[dict] = []
    else:
        thread_id = body.thread_id
        if not threads.thread_belongs_to(landlord_id, thread_id):
            raise HTTPException(status_code=404, detail="Thread not found")
        history = threads.load_history(landlord_id, thread_id)

    try:
        result = run_agent(question, landlord_id=landlord_id, history=history)
    except (ImportError, RuntimeError) as e:
        # Missing requirements-rag.txt deps (groq) or GROQ_API_KEY — a setup
        # problem, not a crash. Mirrors api/routers/rag.py.
        raise HTTPException(status_code=503, detail=f"Assistant not available: {e}")
    except Exception as e:
        # Upstream LLM failure: rate limit, network, model error.
        raise HTTPException(status_code=502, detail=f"Assistant failed: {e}")

    # Persist the turn (plain user + assistant messages; TRD §7).
    threads.append_message(thread_id, "user", question)
    threads.append_message(thread_id, "assistant", result["answer"],
                           tool_calls=result["tools_consulted"] or None)

    return AskResponse(
        answer=result["answer"],
        tools_consulted=result["tools_consulted"],
        thread_id=thread_id,
    )


def _sse(obj: dict) -> str:
    """Serialise one Server-Sent-Events frame. `ensure_ascii=False` keeps German
    umlauts intact on the wire (the response is UTF-8)."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@router.post("/ask/stream")
def ask_stream(body: AskRequest, user: str = Depends(require_auth)) -> StreamingResponse:
    """Streaming twin of /ask (TRD §6). Same contract in, but the answer comes
    back as an SSE token stream instead of one JSON blob.

    Thread resolution + isolation happen *before* streaming starts, so a bad
    thread still returns a normal 404. Once the stream is open the status code is
    already sent, so agent/LLM failures surface as an SSE `{"type":"error"}`
    frame rather than an HTTP error.
    """
    landlord_id = resolve_landlord_id(user)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question must not be empty")

    if body.thread_id is None:
        thread_id = threads.create_thread(landlord_id, title=question[:80])
        history: list[dict] = []
    else:
        thread_id = body.thread_id
        if not threads.thread_belongs_to(landlord_id, thread_id):
            raise HTTPException(status_code=404, detail="Thread not found")
        history = threads.load_history(landlord_id, thread_id)

    def event_stream():
        # Tell the client its thread id up front so follow-ups reuse it.
        yield _sse({"type": "meta", "thread_id": thread_id})
        answer, tools = "", []
        try:
            for ev in run_agent_stream(question, landlord_id=landlord_id, history=history):
                if ev["type"] == "done":
                    answer = ev["answer"]
                    tools = ev["tools_consulted"]
                    yield _sse({"type": "done", "tools_consulted": tools})
                else:
                    # token / tool / tool_result — forward verbatim to the client.
                    yield _sse(ev)
        except (ImportError, RuntimeError) as e:
            yield _sse({"type": "error", "detail": f"Assistant not available: {e}"})
            return
        except Exception as e:
            yield _sse({"type": "error", "detail": f"Assistant failed: {e}"})
            return

        # Persist only on a clean finish (mirrors the non-streaming endpoint).
        threads.append_message(thread_id, "user", question)
        threads.append_message(thread_id, "assistant", answer, tool_calls=tools or None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # tell nginx/ALB not to buffer the stream
        },
    )
