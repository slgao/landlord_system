"""A meter only ever counts up.

The real case this guards: the provider prints its figures without the
decimals, so 788,75 on the invoice is copied in as 788 — a drop of three
quarters of a m³. Nothing downstream can tell that from genuine consumption,
and the subtraction turns into a negative Arbeitskosten that quietly discounts
the bill. Refused at entry it is one corrected digit.
"""
import pytest

import logic
from logic import reading_conflict, reading_rejection


# ── The comparison, with no database in sight ───────────────────────────────

def test_a_reading_below_the_previous_one_is_refused():
    assert reading_conflict(788.0, before=("2026-07-02", 788.75)) == (
        "below_previous", "2026-07-02", 788.75)


def test_a_reading_above_a_later_one_is_refused():
    """Filling in a gap cannot overtake what the meter read afterwards."""
    assert reading_conflict(900.0, after=("2026-10-15", 850.0)) == (
        "above_next", "2026-10-15", 850.0)


def test_an_unchanged_meter_is_accepted():
    """An empty flat consumes nothing, and that is not a meter running back."""
    assert reading_conflict(788.75, before=("2026-07-02", 788.75)) is None


def test_a_reading_between_its_neighbours_is_accepted():
    assert reading_conflict(789.0, before=("2026-07-02", 788.75),
                            after=("2026-10-15", 790.0)) is None


def test_the_first_reading_of_a_meter_is_accepted():
    assert reading_conflict(0.0) is None
    assert reading_conflict(12345.678) is None


def test_the_previous_reading_is_checked_before_the_later_one():
    """Both are wrong; the message should name the one just before it, which is
    the number the user was copying from."""
    kind, when, _ = reading_conflict(10.0, before=("2026-01-01", 20.0),
                                     after=("2026-03-01", 5.0))
    assert (kind, when) == ("below_previous", "2026-01-01")


@pytest.mark.parametrize("delta", [0.0004, -0.0004])
def test_a_rounding_difference_is_the_same_number(delta):
    """Readings are stored to three decimals; less than half a thousandth apart
    is the same number written differently."""
    assert reading_conflict(100.0 + delta, before=("2026-01-01", 100.0)) is None


# ── The refusal message ─────────────────────────────────────────────────────

def _neighbours(monkeypatch, before=None, after=None):
    monkeypatch.setattr(logic, "reading_neighbours",
                        lambda *a, **k: (before, after))


def test_an_acceptable_reading_has_no_message(monkeypatch):
    _neighbours(monkeypatch, before=("2026-07-02", 788.0))
    assert reading_rejection("gas", 3, "2026-08-19", 789.0, owner=1) is None


def test_the_message_names_both_figures_the_date_and_the_unit(monkeypatch):
    _neighbours(monkeypatch, before=("2026-07-02", 788.75))
    msg = reading_rejection("gas", 3, "2026-08-19", 788.0, owner=1)
    assert "788 m³" in msg and "788.75 m³" in msg
    assert "2026-07-02" in msg
    # The actual cause, said out loud, because that is what the user must check.
    assert "decimal point" in msg
    assert "exchanged" in msg          # the one legitimate reason for a drop


def test_the_unit_follows_the_meter_type(monkeypatch):
    _neighbours(monkeypatch, before=("2026-01-01", 500.0))
    assert "kWh" in reading_rejection("strom", 1, "2026-02-01", 400.0, owner=1)
    assert "m³" in reading_rejection("wasser", 1, "2026-02-01", 400.0, owner=1)


def test_a_heizkostenverteiler_reading_is_refused_without_naming_a_unit(monkeypatch):
    """Its unit is whatever its own unit_label says, so the message does not
    guess one."""
    _neighbours(monkeypatch, before=("2026-01-01", 500.0))
    msg = reading_rejection("heizung", 1, "2026-02-01", 400.0, owner=1)
    assert "400 is below the 500" in msg


def test_trailing_zeros_are_not_shown(monkeypatch):
    """The column stores 788.000; the message should not read '788.000'."""
    _neighbours(monkeypatch, before=("2026-07-02", 788.000))
    msg = reading_rejection("gas", 3, "2026-08-19", 700.500, owner=1)
    assert "700.5 m³" in msg and "788 m³" in msg
    assert "788.000" not in msg


def test_a_reading_overtaking_a_later_one_says_so(monkeypatch):
    _neighbours(monkeypatch, after=("2026-10-15", 790.0))
    msg = reading_rejection("gas", 3, "2026-08-19", 900.0, owner=1)
    assert "already recorded later" in msg
    assert "2026-10-15" in msg


# ── The neighbour lookup costs one round trip ───────────────────────────────

def test_the_neighbour_lookup_is_a_single_bundle(monkeypatch):
    seen = []

    def fake_bundle(parts):
        seen.append([n for n, _, _ in parts])
        return {"before": [], "after": []}

    def fail_fetch(*a, **k):
        raise AssertionError("neighbour lookup must not query separately")

    monkeypatch.setattr(logic, "fetch_bundle", fake_bundle)
    monkeypatch.setattr(logic, "fetch", fail_fetch)
    assert logic.reading_neighbours("gas", 3, "2026-08-19", 1) == (None, None)
    assert seen == [["before", "after"]]


def test_the_lookup_excludes_a_row_on_the_same_date(monkeypatch):
    """A reading already standing on this date is the row being replaced, not a
    neighbour — the SQL compares dates strictly."""
    captured = []

    def fake_bundle(parts):
        captured.extend(" ".join(sql.split()) for _, sql, _ in parts)
        return {"before": [], "after": []}

    monkeypatch.setattr(logic, "fetch_bundle", fake_bundle)
    logic.reading_neighbours("gas", 3, "2026-08-19", 1)
    assert any("reading_date < ?" in q for q in captured)
    assert any("reading_date > ?" in q for q in captured)
    assert not any("reading_date <= ?" in q or "reading_date >= ?" in q for q in captured)
