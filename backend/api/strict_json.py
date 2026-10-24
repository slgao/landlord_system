"""Refuse JSON numbers that are not numbers, before they reach a route.

Python's json module accepts three things that are not in the JSON spec and
have no business in an accounting application: the bare literals `NaN`,
`Infinity` and `-Infinity`, and any decimal literal large enough to overflow a
float (`1e400` parses to `inf` without complaint).

Each caused a 500, and two of them caused something worse:

  * `{"amount": NaN}` on POST /api/payments was accepted, 201, and stored — a
    NUMERIC column takes NaN. From then on every report touching that row died
    serialising its response ("Out of range float values are not JSON
    compliant"), so the Payment Reminders page and the Balance Sheet returned
    500 for good, with nothing in the UI able to find or fix the row.

  * `1e400` in *any* field of *any* endpoint — including a field typed `str`,
    which should simply be a 422 — turned the validation error into a 500,
    because the error body FastAPI builds repeats the offending value back and
    Starlette's JSONResponse refuses to serialise a non-finite float.

Validating 83 float fields one by one would have left the next one unguarded,
so the check sits at the door: one parse of the body, applied to every route.
A non-finite number is a client error, and the client is told which field.
"""
from __future__ import annotations

import json
import math

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

# A body larger than this is refused unhashed. Nothing the API accepts as JSON
# comes close — the largest is a signature PNG as a data URL, capped at 2 MB by
# its own field — and without a bound a single request can make the process
# hold an arbitrary amount of memory.
MAX_JSON_BODY = 16 * 1024 * 1024


def find_non_finite(value, path: str = "") -> str | None:
    """Where the first NaN/Infinity sits in a parsed body, in dotted form
    (`billings.0.cost`), or None. Returns "body" for a bare non-finite
    number, which is a valid JSON document on its own."""
    if isinstance(value, float):
        return (path or "body") if not math.isfinite(value) else None
    if isinstance(value, dict):
        for k, v in value.items():
            hit = find_non_finite(v, f"{path}.{k}" if path else str(k))
            if hit:
                return hit
        return None
    if isinstance(value, list):
        for i, v in enumerate(value):
            hit = find_non_finite(v, f"{path}.{i}" if path else str(i))
            if hit:
                return hit
    return None


def _detail(field: str) -> str:
    where = "The body" if field == "body" else f"`{field}`"
    return (f"{where} is not a finite number. NaN, Infinity and numbers too "
            f"large for a 64-bit float are not valid JSON values.")


class RejectNonFiniteNumbers:
    """ASGI middleware. Buffers a JSON body, checks it, and replays it.

    Buffering is the price of checking: the body has to be read here and handed
    on intact. It is bounded by MAX_JSON_BODY and only happens for a JSON
    content type, so multipart uploads (the 5 MB PDFs) stream past untouched.

    Installed *inside* CORSMiddleware so its 422 still carries the CORS
    headers — a response from outside that layer reaches the browser as an
    opaque network error with the reason invisible.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        ctype = Headers(scope=scope).get("content-type", "")
        if "json" not in ctype.split(";")[0].lower():
            return await self.app(scope, receive, send)

        chunks: list[bytes] = []
        size = 0
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                # Nothing to answer: let the app see the disconnect and unwind.
                return await self.app(scope, _replay(b"".join(chunks), receive,
                                                    first=message), send)
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_JSON_BODY:
                return await JSONResponse(
                    {"detail": "The request body is too large."}, status_code=413,
                )(scope, receive, send)
            chunks.append(chunk)
            more = message.get("more_body", False)

        body = b"".join(chunks)
        if body:
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = None        # malformed: FastAPI's own 422 says it better
            field = find_non_finite(parsed)
            if field:
                return await JSONResponse(
                    {"detail": _detail(field)}, status_code=422,
                )(scope, receive, send)

        return await self.app(scope, _replay(body, receive), send)


def _replay(body: bytes, receive, first=None):
    """A `receive` that hands the buffered body over once, then gets out of the way.

    After the body, it delegates to the real `receive` rather than reporting a
    disconnect. That distinction is not academic: a StreamingResponse keeps a
    task on receive() watching for `http.disconnect` and cancels the stream the
    moment it sees one, so a replay that invented a disconnect killed every SSE
    response on the API — /api/assistant/ask/stream answered "Internal Server
    Error" for a perfectly good request. Delegating also means a client that
    really does hang up is still noticed.
    """
    queue = [{"type": "http.request", "body": body, "more_body": False}]
    if first is not None:
        queue.append(first)

    async def replayed():
        if queue:
            return queue.pop(0)
        return await receive()

    return replayed
