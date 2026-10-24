"""What a flat cost actually is, and which record of the mortgage wins.

A mortgage can be on file twice: as a `Mortgage` row in flat_costs, typed from
a bank statement, and as a loan in the `mortgages` table with its terms. Both
are the same money. Counting both charges it twice; picking a different one per
page makes two reports disagree, which is how a 22 € discrepancy between the
balance sheet and the flat economics went unnoticed for months.

So the rule lives here, once, and every report imports it:

    a property's monthly mortgage payment is its LOANS' instalments if it has
    any loan on file, otherwise its `Mortgage` cost rows, and never both.

The fallback is not a nicety. A landlord who has entered the flat's costs but
not yet the loan's terms still has a mortgage, and dropping it would overstate
what the flat earns by the whole instalment.
"""

# Substring matching, because these name a loan however it is written:
# "Mortgage", "Mortgage (Bank)", "Hypothek Sparkasse" are all one thing.
_MORTGAGE_COST_TYPES = ("mortgage", "hypothek", "darlehen", "annuität", "annuitaet",
                        "kredit", "baufinanzierung")

# Rent paid to the flat's owner, on a flat that is sublet rather than owned.
# Matched strictly, not by substring: "Mieterstrom", "Mietkaution" and
# "Mietausfall" are ordinary costs a substring test for "miete" would swallow.
_RENT_TO_OWNER_COST_TYPES = frozenset({
    "miete", "untermiete", "pacht", "mietzahlung", "miete an eigentuemer",
    "miete an eigentümer", "grundmiete",
})


def is_mortgage_cost(cost_type) -> bool:
    name = str(cost_type or "").strip().lower()
    return any(k in name for k in _MORTGAGE_COST_TYPES)


def is_rent_to_owner(cost_type) -> bool:
    return str(cost_type or "").strip().lower() in _RENT_TO_OWNER_COST_TYPES


def resolve_instalment(loan_instalment, mortgage_cost):
    """(instalment, split_known) for one property.

    `loan_instalment` is what the loans on file add up to — None or 0 when the
    property has none. `mortgage_cost` is what its `Mortgage` flat-cost rows
    add up to.

    The loans win where they exist: only their terms say how much of a payment
    is interest and how much buys the flat, and that split drives both the
    operating result and the Schuldzinsen deduction. Where there are none, the
    cost row is the only record of the money and is used as the instalment,
    with the split reported as unknown rather than guessed.
    """
    loan = float(loan_instalment or 0)
    typed = float(mortgage_cost or 0)
    if loan:
        return loan, True
    if typed:
        return typed, False
    return 0.0, True          # nothing owed: nothing unknown about it


# Below this the two records are the same figure written twice, not a conflict.
CONFLICT_TOLERANCE = 0.01


def mortgage_conflict(loan_instalment, mortgage_cost):
    """How far a property's two records of its mortgage disagree, or None.

    Only a property carrying BOTH can conflict. One with just a cost row is the
    supported no-loan case, and one with just loans has nothing to contradict.
    """
    loan = float(loan_instalment or 0)
    typed = float(mortgage_cost or 0)
    if not loan or not typed:
        return None
    diff = typed - loan
    if abs(diff) < CONFLICT_TOLERANCE:
        return None
    return {"loan_instalment": round(loan, 2),
            "mortgage_cost": round(typed, 2),
            "difference": round(diff, 2)}
