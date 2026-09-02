"""Tests for the Übergabeprotokoll module.

The endpoints themselves need a database and are exercised against the dev
instance; what is unit-testable — and what is easy to get quietly wrong — is the
row mapping (a key must not carry a condition, a condition must not carry a
quantity) and the PDF, which has to render for a protocol that is still empty
as well as one full of findings.
"""
import pytest
from fastapi import HTTPException

from api.routers.handover import (
    _row, _item_row, _validate, _require_date, KINDS, CONDITIONS, ITEM_KINDS,
)
from pdfgen import uebergabeprotokoll_pdf, _reading_str


# ── Row mapping ───────────────────────────────────────────────────────────────

def _protocol_row(**kw):
    """A _SELECT row: the 8 columns plus the 4 rolled-up aggregates."""
    base = dict(id=1, contract_id=2, kind="move_out", date="2026-08-31", time=None,
                present=None, note=None, signed=0,
                items=0, defects=0, cost=0, readings=0)
    base.update(kw)
    return (base["id"], base["contract_id"], base["kind"], base["date"], base["time"],
            base["present"], base["note"], base["signed"],
            base["items"], base["defects"], base["cost"], base["readings"])


def test_row_maps_rollups_and_signed_flag():
    p = _row(_protocol_row(signed=1, items=5, defects=2, cost=245.5, readings=3))
    assert p.signed is True
    assert (p.item_count, p.defect_count, p.reading_count) == (5, 2, 3)
    assert p.defect_cost == pytest.approx(245.5)


def test_row_defect_cost_is_zero_not_none_when_nothing_found():
    # COALESCE keeps SUM() from returning NULL, but a None must still not reach
    # the client as null — the frontend does arithmetic on this field.
    p = _row(_protocol_row(cost=None))
    assert p.defect_cost == 0.0


def test_row_treats_the_string_none_as_no_date():
    # Legacy rows in this database store the *string* 'None' for a missing date
    # (see the backfill_none_string_dates migration).
    assert _row(_protocol_row(date="None")).date == ""
    assert _row(_protocol_row(date=None)).date == ""


def test_item_row_keeps_a_condition_free_of_quantity():
    it = _item_row((1, 7, "condition", "Küche", "defect", None, 180.0, "Parkett", 0))
    assert it.condition == "defect"
    assert it.quantity is None
    assert it.estimated_cost == pytest.approx(180.0)


def test_item_row_keeps_a_key_free_of_condition():
    it = _item_row((2, 7, "key", "Wohnungstür", None, 2, None, None, 0))
    assert it.kind == "key"
    assert it.quantity == 2
    assert it.condition is None


# ── Validation ────────────────────────────────────────────────────────────────

def test_validate_accepts_the_known_vocabulary():
    for k in KINDS:
        _validate(k, KINDS, "kind")
    for c in CONDITIONS:
        _validate(c, CONDITIONS, "condition")
    for k in ITEM_KINDS:
        _validate(k, ITEM_KINDS, "item kind")


def test_validate_rejects_anything_else_as_422():
    with pytest.raises(HTTPException) as exc:
        _validate("midterm", KINDS, "kind")
    assert exc.value.status_code == 422


def test_the_three_conditions_are_exactly_the_legal_distinction():
    # 'wear' (normale Abnutzung) may not be charged to the tenant, 'defect'
    # (Mangel) may. Adding a fourth value silently changes what the deposit
    # bridge in the frontend will offer to deduct, so pin the vocabulary.
    assert CONDITIONS == ("ok", "wear", "defect")


def test_require_date_rejects_an_undated_protocol():
    # An undated reading would not fail the Nebenkostenabrechnung, it would
    # quietly skew it — so refuse the write instead.
    for bad in ("", None, "None"):
        with pytest.raises(HTTPException) as exc:
            _require_date(bad)
        assert exc.value.status_code == 422


def test_require_date_passes_a_real_date_through():
    assert _require_date("2026-08-31") == "2026-08-31"


# ── Readings formatting ───────────────────────────────────────────────────────

def test_reading_str_drops_the_trailing_zeros_of_a_whole_meter():
    assert _reading_str(14523.0) == "14523"


def test_reading_str_keeps_real_decimals():
    assert _reading_str(342.517) == "342.517"
    assert _reading_str(8891.25) == "8891.25"


def test_reading_str_survives_none_and_zero():
    assert _reading_str(None) == "0"
    assert _reading_str(0) == "0"


# ── PDF ───────────────────────────────────────────────────────────────────────

def _pdf(**kw):
    args = dict(
        protocol={"kind": "move_out", "date": "2026-08-31", "time": None,
                  "present_persons": None, "note": None, "signed": False},
        tenant_name="Test Tenant", co_tenant_names=[],
        apartment_name="Zimmer 1", property_name="Testhaus",
        address="Teststr. 5, 10115 Berlin",
        conditions=[], keys=[], readings=[], landlord_name="Hausverwaltung",
    )
    args.update(kw)
    return uebergabeprotokoll_pdf(**args)


def test_pdf_renders_for_a_protocol_with_nothing_filled_in():
    # The blank sheet is a real use: print it, walk the flat, write on it.
    out = _pdf()
    assert out[:4] == b"%PDF"
    assert len(out) > 1000


def test_pdf_renders_a_full_move_out():
    out = _pdf(
        protocol={"kind": "move_out", "date": "2026-08-31", "time": "14:00",
                  "present_persons": "Vermieter, Mieterin",
                  "note": "Rest nach der Abrechnung.", "signed": True},
        co_tenant_names=["Second Tenant"],
        conditions=[{"area": "Küche", "condition": "ok", "estimated_cost": None, "note": ""},
                    {"area": "Bad", "condition": "wear", "estimated_cost": None, "note": "Fugen"},
                    {"area": "Diele", "condition": "defect", "estimated_cost": 180.0, "note": "Parkett"}],
        keys=[{"area": "Wohnungstür", "quantity": 2, "note": ""}],
        readings=[{"meter_type": "strom", "reading": 14523.0,
                   "serial_number": "1ESY0012", "description": "Zimmer 1", "note": None}],
    )
    assert out[:4] == b"%PDF"


def test_pdf_renders_a_move_in():
    assert _pdf(protocol={"kind": "move_in", "date": "2024-03-01", "time": None,
                          "present_persons": None, "note": None, "signed": False})[:4] == b"%PDF"


def test_pdf_survives_a_missing_or_malformed_date():
    # An unsaved protocol can reach the PDF with an empty date; it must render
    # rather than raise, because the sheet is often printed before it is filled.
    for d in ("", None, "not-a-date"):
        assert _pdf(protocol={"kind": "move_in", "date": d, "time": None,
                              "present_persons": None, "note": None,
                              "signed": False})[:4] == b"%PDF"


def test_pdf_handles_a_defect_without_an_estimate():
    # A Mangel whose cost is not yet known must not print "0.00 €" as if it
    # were free, and must not break the defect summary line.
    out = _pdf(conditions=[{"area": "Fenster", "condition": "defect",
                            "estimated_cost": None, "note": "Griff lose"}])
    assert out[:4] == b"%PDF"
