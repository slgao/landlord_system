"""Which record of the mortgage wins, and when the two disagree.

A mortgage can be on file twice — a `Mortgage` flat-cost row typed from a bank
statement, and a loan with its terms. Counting both charges it twice; picking a
different one per page makes two reports disagree, which is exactly how a 22 €
gap between the balance sheet and the flat economics went unnoticed.
"""
import pytest

from cost_types import (is_mortgage_cost, is_rent_to_owner, mortgage_conflict,
                        resolve_instalment)


# ── Which record wins ────────────────────────────────────────────────────────

def test_the_loans_win_when_both_are_on_file():
    """Only the loan's terms split interest from Tilgung, and that split drives
    both the operating result and the Schuldzinsen deduction."""
    assert resolve_instalment(643.75, 641.84) == (643.75, True)


def test_a_typed_cost_row_is_used_when_there_is_no_loan():
    """The scenario that matters for a new user: costs entered, loan terms not
    yet. Dropping it would overstate the flat by the whole instalment."""
    assert resolve_instalment(None, 656.74) == (656.74, False)
    assert resolve_instalment(0, 656.74) == (656.74, False)


def test_a_loan_alone_is_used_and_its_split_is_known():
    assert resolve_instalment(460.42, 0) == (460.42, True)
    assert resolve_instalment(460.42, None) == (460.42, True)


def test_a_flat_with_no_mortgage_at_all_owes_nothing_and_hides_nothing():
    """Nothing is unknown about a flat that has no mortgage."""
    assert resolve_instalment(None, None) == (0.0, True)
    assert resolve_instalment(0, 0) == (0.0, True)


def test_the_two_records_are_never_added_together():
    """The bug this rule exists to prevent."""
    instalment, _ = resolve_instalment(643.75, 641.84)
    assert instalment == 643.75
    assert instalment != pytest.approx(643.75 + 641.84)


# ── The consistency check ────────────────────────────────────────────────────

def test_a_disagreement_between_the_two_records_is_reported():
    c = mortgage_conflict(506.29, 530.25)
    assert c == {"loan_instalment": 506.29, "mortgage_cost": 530.25,
                 "difference": 23.96}


def test_the_difference_is_signed_so_its_direction_is_visible():
    c = mortgage_conflict(643.75, 641.84)
    assert c["difference"] == pytest.approx(-1.91)


def test_records_that_agree_are_not_a_conflict():
    assert mortgage_conflict(687.93, 687.93) is None


def test_a_sub_cent_difference_is_the_same_figure_written_twice():
    assert mortgage_conflict(500.00, 500.004) is None


def test_only_a_cost_row_is_not_a_conflict():
    """The supported no-loan case. Flagging it would nag every user who has
    not entered their loan terms."""
    assert mortgage_conflict(None, 656.74) is None
    assert mortgage_conflict(0, 656.74) is None


def test_only_loans_is_not_a_conflict():
    assert mortgage_conflict(460.42, None) is None
    assert mortgage_conflict(460.42, 0) is None


def test_no_mortgage_at_all_is_not_a_conflict():
    assert mortgage_conflict(None, None) is None


# ── Classification ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["Mortgage", "mortgage", "Hypothek", "Darlehen",
                                  "Annuität", "Kredit", "Baufinanzierung",
                                  "Mortgage (Sparkasse)"])
def test_the_ways_a_mortgage_cost_is_named(name):
    assert is_mortgage_cost(name) is True


@pytest.mark.parametrize("name", ["Hausgeld", "Grundsteuer", "Internet", "Miete",
                                  "Rundfunk", "", None])
def test_a_running_cost_is_not_a_mortgage(name):
    assert is_mortgage_cost(name) is False


def test_rent_to_an_owner_is_matched_strictly():
    assert is_rent_to_owner("Miete") is True
    assert is_rent_to_owner("Mieterstrom") is False
