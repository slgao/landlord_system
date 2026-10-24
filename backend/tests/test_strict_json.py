"""Non-finite numbers are refused at the door, and said to be the client's.

The case that made this necessary: `{"amount": NaN}` was accepted and stored
in a NUMERIC column, after which every report that summed it answered 500 —
permanently, with no way to find the row from the UI.
"""
import json
import math

import pytest

from api.errors import db_error_response
from api.strict_json import MAX_JSON_BODY, find_non_finite, _detail


# ── Where the bad number is ──────────────────────────────────────────────────

def test_a_clean_body_passes():
    assert find_non_finite({"amount": 1200.5, "note": "Miete", "ok": [1, 2, 3]}) is None


def test_nan_is_found_and_named():
    assert find_non_finite({"amount": float("nan")}) == "amount"


def test_infinity_is_found():
    assert find_non_finite({"amount": float("inf")}) == "amount"
    assert find_non_finite({"amount": float("-inf")}) == "amount"


def test_a_nested_field_is_named_in_full():
    body = {"strom": [{"cost": 1.0}, {"cost": float("nan")}]}
    assert find_non_finite(body) == "strom.1.cost"


def test_a_bare_non_finite_document_is_called_body():
    assert find_non_finite(float("nan")) == "body"


def test_a_string_that_merely_says_nan_is_not_a_number():
    # Only the JSON *number* is refused here. "NaN" as text is a string, and
    # whichever field it lands in rejects it on its own terms.
    assert find_non_finite({"note": "NaN", "amount": 1}) is None


def test_integers_and_none_are_left_alone():
    assert find_non_finite({"a": 1, "b": None, "c": True, "d": "x"}) is None


# ── What Python's json actually parses ───────────────────────────────────────

@pytest.mark.parametrize("raw", ['{"amount": NaN}', '{"amount": Infinity}',
                                 '{"amount": -Infinity}', '{"amount": 1e400}'])
def test_python_accepts_these_so_the_check_has_to_catch_them(raw):
    # The reason this middleware exists: json.loads takes all four, so by the
    # time pydantic sees the value it is already inf or nan.
    parsed = json.loads(raw)
    assert not math.isfinite(parsed["amount"])
    assert find_non_finite(parsed) == "amount"


def test_a_large_but_finite_number_is_allowed_through():
    # 1e308 is a real number; whether the column takes it is the database's
    # business, and it answers with a 422 of its own (see below).
    assert find_non_finite(json.loads('{"amount": 1e308}')) is None


# ── The message ──────────────────────────────────────────────────────────────

def test_the_message_names_the_field():
    assert "`amount`" in _detail("amount")


def test_the_message_for_a_bare_body_does_not_pretend_to_name_a_field():
    assert _detail("body").startswith("The body")


def test_the_body_cap_is_generous_but_finite():
    assert 1_000_000 < MAX_JSON_BODY <= 64 * 1024 * 1024


# ── A value the schema will not take is a 422, not a crash ───────────────────

class _PGError(Exception):
    def __init__(self, pgcode):
        self.pgcode = pgcode


@pytest.mark.parametrize("code,status", [
    ("22003", 422),       # numeric field overflow — living_sqm: 999999999999
    ("22001", 422),       # value too long for the column
    ("23505", 409),       # unique violation
    ("23503", 409),       # foreign key violation
    ("23502", 422),       # not-null violation
])
def test_a_refusal_by_the_schema_is_reported_as_the_callers(code, status):
    got_status, detail = db_error_response(_PGError(code))
    assert got_status == status
    assert detail and detail[0].isupper() and detail.endswith(".")


def test_an_outage_is_still_ours():
    # Connection failure, syntax error, permission denied: not the caller's
    # fault, and calling it a 422 would hide a real fault behind a form error.
    assert db_error_response(_PGError("08006")) is None
    assert db_error_response(_PGError("42601")) is None
    assert db_error_response(_PGError(None)) is None
    assert db_error_response(ValueError("not a database error at all")) is None


def test_the_detail_never_repeats_the_database_text():
    # psycopg2's message carries the host, the user and the schema.
    exc = _PGError("22003")
    exc.args = ("numeric field overflow on relation properties at 10.0.0.5",)
    status, detail = db_error_response(exc)
    assert "10.0.0.5" not in detail and "properties" not in detail
    assert detail == "A number is too large for the field it goes in."


# ── A utility section that is not an object ──────────────────────────────────

def test_a_billing_section_that_is_not_an_object_is_refused():
    from fastapi import HTTPException
    from api.routers.reports import _norm_billings

    assert _norm_billings(None) == []
    assert _norm_billings({"eff_days": 30}) == [{"eff_days": 30}]
    assert _norm_billings([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]

    # `{"strom": -1}` used to reach `(-1).get("eff_days")` and answer 500.
    for bad in (-1, "text", True, [1], [{"ok": 1}, "text"]):
        with pytest.raises(HTTPException) as e:
            _norm_billings(bad, "Strom")
        assert e.value.status_code == 422
        assert "Strom" in e.value.detail


# ── The storage path, where a string "NaN" arrives as a float ────────────────

def test_a_non_finite_bound_parameter_is_refused():
    import db

    # Clean parameters, including the types most statements actually bind.
    db._reject_non_finite(None)
    db._reject_non_finite(())
    db._reject_non_finite((1, "Miete", None, True, 1050.25))
    db._reject_non_finite({"a": 1, "b": "x"})

    from decimal import Decimal
    for bad in (float("nan"), float("inf"), float("-inf"),
                Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(db.NonFiniteNumber):
            db._reject_non_finite((1, bad, "2026-01-05"))
        with pytest.raises(db.NonFiniteNumber):
            db._reject_non_finite({"amount": bad})


def test_the_api_reports_that_refusal_as_the_callers_mistake():
    import db
    status, detail = db_error_response(db.NonFiniteNumber("nope"))
    assert status == 422
    assert "finite" in detail


def test_a_string_saying_nan_reaches_the_storage_guard():
    # pydantic coerces "NaN" to float('nan') for a float field, so the body
    # check at the door never sees a JSON number. This is the net under it.
    import db
    assert find_non_finite({"amount": "NaN"}) is None
    with pytest.raises(db.NonFiniteNumber):
        db._reject_non_finite((float("NaN"),))


# ── A name is a name, not a number ───────────────────────────────────────────

def test_the_balance_sheet_keeps_a_flats_name_as_text(monkeypatch):
    from decimal import Decimal
    import balance_compute
    from api.routers import reports

    # One flat per awkward name, with Decimal money beside it.
    names = ["NaN", "inf", "Infinity", "12", "1e400", "Einbeckerstr."]
    snapshot = [{"name": n, "expected": Decimal("1000.00"),
                 "costs": Decimal("250.50"), "net": Decimal("749.50")} for n in names]
    props = [{"name": n, "monthly_rows": [{"Month": "Jan 2025",
                                           "Expected rent (€)": Decimal("1000.00")}],
              "tot_expected": Decimal("1000"), "tot_actual": Decimal("900"),
              "tot_costs": Decimal("250.50"), "tot_one_off": Decimal("0"),
              "tot_settlements": Decimal("0")} for n in names]
    monkeypatch.setattr(balance_compute, "_compute_snapshot",
                        lambda year, owner, one_off: (snapshot, props))

    out = reports.balance_sheet_data(year=2025, include_one_off=False, owner=1)

    # Every name survives as the text it is: "12" was coming back as 12.0, and
    # "NaN"/"inf" became non-finite floats that 500ed the whole response.
    assert [row["name"] for row in out["snapshot"]] == names
    assert [p["name"] for p in out["properties"]] == names
    assert find_non_finite(out) is None
    # …while the money is plain floats, which is what this conversion is for.
    assert out["snapshot"][0]["expected"] == 1000.0
    assert isinstance(out["snapshot"][0]["costs"], float)
    assert out["properties"][0]["monthly_rows"][0]["Expected rent (€)"] == 1000.0
    assert out["properties"][0]["monthly_rows"][0]["Month"] == "Jan 2025"


# ── The body has to reach the route unchanged, and streaming must survive ────

def _run(coro):
    import asyncio
    return asyncio.run(coro)


def _scope(method="POST", ctype="application/json"):
    return {"type": "http", "method": method, "path": "/api/x",
            "headers": [(b"content-type", ctype.encode())]}


def _collect(app_calls):
    """A tiny ASGI app that records what body it was given."""
    async def app(scope, receive, send):
        chunks = []
        while True:
            m = await receive()
            if m["type"] != "http.request":
                break
            chunks.append(m.get("body", b""))
            if not m.get("more_body"):
                break
        app_calls.append(b"".join(chunks))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    return app


def test_a_clean_body_arrives_whole_even_when_split_across_chunks():
    from api.strict_json import RejectNonFiniteNumbers
    got, sent = [], []

    async def receive():
        # Two chunks, as a chunked upload arrives.
        if not hasattr(receive, "n"):
            receive.n = 1
            return {"type": "http.request", "body": b'{"amount": 10', "more_body": True}
        return {"type": "http.request", "body": b'50.25}', "more_body": False}

    async def send(message):
        sent.append(message)

    _run(RejectNonFiniteNumbers(_collect(got))(_scope(), receive, send))
    assert got == [b'{"amount": 1050.25}']
    assert sent[0]["status"] == 200


def test_a_non_finite_body_never_reaches_the_route():
    from api.strict_json import RejectNonFiniteNumbers
    got, sent = [], []

    async def receive():
        return {"type": "http.request", "body": b'{"amount": NaN}', "more_body": False}

    async def send(message):
        sent.append(message)

    _run(RejectNonFiniteNumbers(_collect(got))(_scope(), receive, send))
    assert got == []                              # the route was never called
    assert sent[0]["status"] == 422


def test_a_non_json_body_is_not_buffered_at_all():
    # The 5 MB PDF uploads are multipart; they must stream past untouched.
    from api.strict_json import RejectNonFiniteNumbers
    seen = []

    async def app(scope, receive, send):
        seen.append("called")
        assert (await receive())["body"] == b"--boundary--"

    async def receive():
        return {"type": "http.request", "body": b"--boundary--", "more_body": False}

    async def send(message):
        pass

    _run(RejectNonFiniteNumbers(app)(_scope(ctype="multipart/form-data; boundary=x"),
                                     receive, send))
    assert seen == ["called"]


def test_a_get_is_passed_straight_through():
    from api.strict_json import RejectNonFiniteNumbers
    seen = []

    async def app(scope, receive, send):
        seen.append("called")

    async def receive():
        raise AssertionError("a GET body must not be read")

    _run(RejectNonFiniteNumbers(app)(_scope(method="GET"), receive, lambda m: None))
    assert seen == ["called"]


def test_the_route_keeps_listening_for_a_real_disconnect():
    # A StreamingResponse watches receive() for http.disconnect and cancels
    # the moment it sees one. The replay must therefore delegate to the real
    # receive after the body instead of inventing a disconnect — that broke
    # every SSE response on the API.
    from api.strict_json import _replay
    events = [{"type": "http.disconnect"}]

    async def real_receive():
        return events.pop(0) if events else {"type": "nothing.left"}

    replayed = _replay(b'{"question": "x"}', real_receive)
    first = _run(replayed())
    assert first == {"type": "http.request", "body": b'{"question": "x"}',
                     "more_body": False}
    # Only now, and only because the client really did hang up.
    assert _run(replayed()) == {"type": "http.disconnect"}
    assert _run(replayed()) == {"type": "nothing.left"}


def test_an_oversized_body_is_refused_before_it_is_parsed():
    from api.strict_json import RejectNonFiniteNumbers, MAX_JSON_BODY
    got, sent = [], []
    chunk = b"x" * (1024 * 1024)
    left = {"n": MAX_JSON_BODY // len(chunk) + 2}

    async def receive():
        left["n"] -= 1
        return {"type": "http.request", "body": chunk, "more_body": left["n"] > 0}

    async def send(message):
        sent.append(message)

    _run(RejectNonFiniteNumbers(_collect(got))(_scope(), receive, send))
    assert got == []
    assert sent[0]["status"] == 413


# ── The one section that is a list of items, not a billing ──────────────────

def test_the_extra_positions_section_is_checked_too():
    from fastapi import HTTPException
    from api.routers.reports import _check_extra

    # Absent, empty, a bare list, and the legacy wrapper all pass.
    _check_extra(None)
    _check_extra([])
    _check_extra({})
    _check_extra([{"description": "Schlüsselverlust", "amount": 50.0}])
    _check_extra({"items": [{"description": "Schlüsselverlust", "amount": 50}]})
    # An item with no description is ignored by the PDF, so it needs no amount.
    _check_extra([{"amount": None}])

    for bad in (-1, "text", True, [1], [{"ok": 1}, "text"], {"items": 7}):
        with pytest.raises(HTTPException) as e:
            _check_extra(bad)
        assert e.value.status_code == 422

    # A described position with no amount would fail summing the subtotal.
    with pytest.raises(HTTPException) as e:
        _check_extra([{"description": "Schlüsselverlust"}])
    assert e.value.status_code == 422
    assert "Schlüsselverlust" in e.value.detail
