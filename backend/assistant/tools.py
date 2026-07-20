"""Tool schemas + dispatch + the read-only data tools (TRD §3, §4, §5).

Two things the model interacts with:

  * `TOOL_SCHEMAS`  — the JSON the model reads to decide *what* to call. The
    `description` fields are prompts: write them like you're telling a new
    employee when to reach for each tool. **No tool declares a `landlord_id`
    parameter** — the model must have no vocabulary for widening its scope.
  * `dispatch`      — how we *execute* a call the model asked for. `landlord_id`
    is injected here by the loop from the verified JWT; the model never supplies
    it, and `dispatch` strips any it hallucinates.

Design rules that make R1/R3 enforceable rather than requested:
  * Scope is a hard gate (`require_scope`, Phase 1) → SQL `WHERE landlord_id = ?`
    + RLS (Phase 2). There is no code path that returns rows unscoped.
  * Reuse audited logic — `logic.detect_overdue`, `tax.build_report` — instead of
    reimplementing business rules, so the assistant can never drift from the app.
  * Tools return small JSON-able dicts. Errors are *return values*
    (`{"error": ...}`), not exceptions, so a bad call degrades to a message the
    model can relay instead of 500-ing the request.
  * The registry contains only reads. Phase 3 writes go in a *separate* registry
    behind confirmation — keeping them apart now is why "read-only" is structural.
"""

from __future__ import annotations

from functools import lru_cache

import db
import logic
from .guardrails import require_scope


# ── Tool schemas the model sees (TRD §3) ────────────────────────────────────
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_overdue_rent",
            "description": (
                "List tenants who are behind on rent, with the amount owed and "
                "how many months they are overdue. Use for 'who owes me money', "
                "'which tenants are in arrears', rent-arrears questions."
            ),
            "parameters": {"type": "object", "properties": {}},  # no args → no scope leak
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_apartments",
            "description": (
                "List all apartments in the portfolio with their id, name and "
                "property. Call this first to get an apartment_id before asking "
                "for a specific contract, payments or Kaution."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contract",
            "description": (
                "Contract terms for one apartment: tenant, cold rent (Kaltmiete), "
                "Kaution, start/end date, and monthly Nebenkosten-Vorauszahlung. "
                "Needs an apartment_id from list_apartments."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "apartment_id": {
                        "type": "integer",
                        "description": "Apartment id from list_apartments.",
                    }
                },
                "required": ["apartment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_payments",
            "description": (
                "Recent rent payments recorded for one apartment's active "
                "contract, most recent first. Needs an apartment_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "apartment_id": {
                        "type": "integer",
                        "description": "Apartment id from list_apartments.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many recent payments to return (default 12).",
                    },
                },
                "required": ["apartment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tax_report",
            "description": (
                "Landlord tax summary for a given year across tax-relevant "
                "properties: rental income, AfA (depreciation), deductible "
                "expenses and mortgage interest. Use for tax / AfA / "
                "Werbungskosten questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Calendar year, e.g. 2025.",
                    }
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_legal_corpus",
            "description": (
                "Search German tenancy law (BetrKV, BGB §§551/556) and the Vermio "
                "docs. Use for legal rules, limits, definitions — e.g. the maximum "
                "Kaution, which costs are umlagefähig, Nebenkosten deadlines."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]


# ── Data tools (read-only, landlord-scoped) ─────────────────────────────────
# Phase 1: the scope is enforced by `require_scope` because the schema has no
# `landlord_id` column yet. Each query below is marked with the Phase-2 predicate
# it will grow (`AND p.landlord_id = ?`), so the migration is a fill-in, not a
# redesign (TRD §6, §11).

def _get_overdue_rent(landlord_id: int) -> dict:
    require_scope(landlord_id)
    # Reuse the audited overdue logic verbatim. Phase 2:
    # logic.detect_overdue(landlord_id=landlord_id).
    overdue = logic.detect_overdue()
    return {
        "count": len(overdue),
        "tenants": [
            {
                "tenant": o["tenant"],
                "apartment": o["apartment"],
                "property": o["property_name"],
                "months_due": o["months_due"],
                "amount_due": o["amount_due"],
                "currency": o["currency"],
            }
            for o in overdue
        ],
    }


def _list_apartments(landlord_id: int) -> dict:
    require_scope(landlord_id)
    rows = db.fetch(
        """SELECT a.id, a.name, p.name
           FROM apartments a
           JOIN properties p ON p.id = a.property_id
           -- Phase 2 adds: WHERE p.landlord_id = <scope>
           ORDER BY p.name, a.name"""
    )
    return {
        "apartments": [
            {"apartment_id": aid, "apartment": aname, "property": pname}
            for aid, aname, pname in rows
        ]
    }


def _get_contract(landlord_id: int, apartment_id: int) -> dict:
    require_scope(landlord_id)
    rows = db.fetch(
        """SELECT t.name, c.rent, c.kaution_amount, c.start_date, c.end_date,
                  c.nebenkosten_vorauszahlung, COALESCE(c.currency, 'EUR')
           FROM contracts c
           JOIN apartments a ON a.id = c.apartment_id
           JOIN properties p ON p.id = a.property_id
           JOIN tenants   t ON t.id = c.tenant_id
           WHERE a.id = ? AND COALESCE(c.terminated, 0) = 0""",
        # Phase 2: AND p.landlord_id = ?
        (apartment_id,),
    )
    if not rows:
        return {"error": "no active contract found for that apartment in your portfolio"}
    name, rent, kaution, start, end, nkv, currency = rows[0]
    return {
        "tenant": name,
        "kaltmiete": float(rent),
        "kaution": float(kaution or 0),
        "nebenkosten_vorauszahlung": float(nkv or 0),
        "start_date": start,
        "end_date": end,
        "currency": currency,
    }


def _get_payments(landlord_id: int, apartment_id: int, limit: int = 12) -> dict:
    require_scope(landlord_id)
    limit = max(1, min(int(limit), 60))
    rows = db.fetch(
        """SELECT pm.payment_date, pm.amount, COALESCE(pm.currency, 'EUR')
           FROM payments pm
           JOIN contracts c ON c.id = pm.contract_id
           JOIN apartments a ON a.id = c.apartment_id
           JOIN properties p ON p.id = a.property_id
           WHERE a.id = ? AND COALESCE(c.terminated, 0) = 0
           -- Phase 2 adds: AND p.landlord_id = <scope>
           ORDER BY pm.payment_date DESC
           LIMIT ?""",
        (apartment_id, limit),
    )
    return {
        "count": len(rows),
        "payments": [
            {"date": d, "amount": float(amt), "currency": cur}
            for d, amt, cur in rows
        ],
    }


def _get_tax_report(landlord_id: int, year: int) -> dict:
    require_scope(landlord_id)
    # Import here so the base app / other tools don't drag in the tax module
    # unless a tax question is actually asked.
    from api.routers.tax import build_report

    report, excluded = build_report(int(year))  # Phase 2: build_report(year, landlord_id)
    return {
        "year": int(year),
        "properties": report,
        "excluded_properties": excluded,
    }


# ── Legal corpus tool (global, NOT landlord-scoped) — TRD §5 ────────────────
# The law is identical for every landlord, so this tool takes no scope. Do not
# "helpfully" add a landlord filter here — it would break the shared corpus.
@lru_cache(maxsize=1)
def _pipeline():
    # Lazy import mirrors api/routers/rag.py: the RAG deps (sentence-transformers,
    # chromadb, groq) live in requirements-rag.txt, not the base image.
    from rag.generate import GroqGenerator
    from rag.pipeline import RagPipeline

    return RagPipeline(generator=GroqGenerator())


def _search_legal_corpus(query: str) -> dict:
    # Return retrieved+reranked passages as data for the AGENT to reason over,
    # plus the pipeline's own grounded answer and citations.
    r = _pipeline().ask(query)
    if r.refused:
        return {"found": False, "note": "no confident legal source for that query"}
    return {
        "found": True,
        "answer": r.answer,
        "citations": r.citations,
        "snippets": [c.text[:400] for c in r.retrieved],
    }


# ── Dispatch (TRD §4) ───────────────────────────────────────────────────────
# name → (landlord_id, args) -> dict. `search_legal_corpus` ignores the scope
# because the corpus is global.
_DISPATCH = {
    "get_overdue_rent":    lambda lid, a: _get_overdue_rent(lid),
    "list_apartments":     lambda lid, a: _list_apartments(lid),
    "get_contract":        lambda lid, a: _get_contract(lid, int(a["apartment_id"])),
    "get_payments":        lambda lid, a: _get_payments(lid, int(a["apartment_id"]),
                                                        int(a.get("limit", 12))),
    "get_tax_report":      lambda lid, a: _get_tax_report(lid, int(a["year"])),
    "search_legal_corpus": lambda lid, a: _search_legal_corpus(str(a["query"])),
}


def dispatch(name: str, args: dict, landlord_id: int) -> dict:
    """Execute the tool the model asked for, binding the trusted `landlord_id`.

    THE SECURITY BOUNDARY: `landlord_id` is passed in by the loop from the
    verified JWT, never from `args`. We strip any `landlord_id` the model tried
    to smuggle into the arguments (belt & braces on top of the schemas simply
    not declaring one), then call the tool. Tool errors become return values so
    a bad call never crashes the request.
    """
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    args = args if isinstance(args, dict) else {}   # tolerate null/non-object args
    args.pop("landlord_id", None)   # strip any faked scope the model invented
    try:
        return fn(landlord_id, args)
    except KeyError as e:
        return {"error": f"missing required argument {e}"}
    except Exception as e:          # incl. ScopeError — surfaced as data, not a crash
        return {"error": str(e)}
