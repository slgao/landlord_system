"""What each flat actually earns.

Three different questions get confused in a rental portfolio, and this module
keeps them apart because the answers often disagree:

- **Cashflow** — what the bank account sees: rent in, flat costs out, the whole
  mortgage instalment out. This is what tells you whether a flat needs feeding
  each month.
- **Operating result** — rent less costs less *interest*. The Tilgung part of
  an instalment is not a cost: it buys the flat. A flat can be cashflow
  negative and still be earning, and that distinction is the difference between
  a bad investment and a fast repayment.
- **Yield** — the return on what the flat is worth, which is how it compares
  with anything else you could own instead.

Every figure is per month unless it says otherwise, and nothing here is
annualised from a partial month: the rent is the rent currently contracted, not
an average of what happened to arrive.
"""
from decimal import Decimal

# Re-exported: the tests and the routers import them from here, and the
# balance sheet imports them from cost_types. One definition, two doors.
from cost_types import (is_mortgage_cost, is_rent_to_owner,  # noqa: F401
                        mortgage_conflict, resolve_instalment)
from tax_logic import monthly_equivalent

_ZERO = Decimal("0")


def _blank(v) -> bool:
    """Date columns are TEXT and some legacy rows hold the string 'None'."""
    return v is None or str(v) in ("None", "")


def contracted_rent(contracts, on_date: str):
    """Rent currently contracted for one flat, and which rooms are let.

    `contracts` is [(apartment_id, rent, start_date, end_date, terminated, id)].

    One contract per apartment, the most recently started among those running
    on `on_date` — the same rule the balance sheet uses, and for the same
    reason: a stale end_date on an old contract must not make a room pay twice.
    A terminated contract is not running, whatever its dates say.

    Returns (rent, {apartment_id: rent}).
    """
    best: dict = {}
    for apt, rent, start, end, terminated, cid in contracts:
        if terminated:
            continue
        if _blank(start) or str(start) > on_date:
            continue
        if not _blank(end) and str(end) < on_date:
            continue
        rank = (str(start), cid)
        if apt not in best or rank > best[apt][0]:
            best[apt] = (rank, Decimal(str(rent)))
    return sum((r for _, r in best.values()), _ZERO), {a: r for a, (_, r) in best.items()}


def recurring_costs(cost_rows, on_date: str) -> Decimal:
    """Monthly cost of the flat's recurring charges in force on `on_date`.

    `cost_rows` is [(amount, frequency, valid_from, valid_to)] or the same with
    a cost_type first — see split_costs, which is what callers with a mortgage
    to account for should use.

    A quarterly or annual charge is spread over its months, exactly as the
    balance sheet does it. A one-time cost is not a recurring charge and is
    left out: it belongs to the month it was paid, not to every month.

    Only rows in force on the day count — a superseded price (Hausgeld raised
    from 355 to 358) must not be added to its own successor.
    """
    total = _ZERO
    for row in cost_rows:
        amount, freq, valid_from, valid_to = row[-4:]
        if freq == "one-time":
            continue
        if not _blank(valid_from) and str(valid_from) > on_date:
            continue
        if not _blank(valid_to) and str(valid_to) < on_date:
            continue
        # Decimal before the division, not after: monthly_equivalent keeps
        # whatever precision it is handed, and a quarterly 300 must stay 100.
        total += monthly_equivalent(Decimal(str(amount)), freq)
    return total


def split_costs(cost_rows, on_date: str):
    """(running costs, mortgage, rent paid to the owner) for one flat.

    `cost_rows` is [(cost_type, amount, frequency, valid_from, valid_to)].

    All three are real money, and all three are subtracted — they are separated
    only because they answer different questions:

    - the mortgage is not a running cost at all: part of every instalment buys
      the flat, so it needs the interest/Tilgung split the loan's terms give;
    - rent paid to an owner is the dominant cost of a sublet and the thing its
      margin is measured against, so burying it among the Hausgeld and the
      internet hides what the arrangement actually earns.
    """
    running, mortgage, to_owner = [], [], []
    for r in cost_rows:
        if is_mortgage_cost(r[0]):
            mortgage.append(r)
        elif is_rent_to_owner(r[0]):
            to_owner.append(r)
        else:
            running.append(r)
    return (recurring_costs(running, on_date),
            recurring_costs(mortgage, on_date),
            recurring_costs(to_owner, on_date))


def economics(*, rent, costs, instalment=0.0, interest=0.0, value=None,
              debt=0.0, rooms=0, let_rooms=0, arrears=0.0, rent_to_owner=0.0):
    """One flat's monthly economics, and the yields that follow from them.

    `instalment` is the full monthly mortgage payment and `interest` the part
    of it that is interest; the remainder buys equity and is not a cost.
    `value` may be None — a flat with no valuation still has a cashflow, and
    saying so is better than withholding the whole row.
    """
    rent_f = float(rent or 0)
    costs_f = float(costs or 0)
    to_owner = float(rent_to_owner or 0)
    inst = float(instalment or 0)
    # The split is unknown when the instalment comes from a flat-cost row and
    # the loan's terms are not on file. Cashflow is still exact; the operating
    # result is not knowable, and claiming one would be a guess at how much of
    # the payment is interest.
    known = interest is not None
    int_f = min(float(interest or 0), inst)      # never more than is actually paid
    principal = inst - int_f if known else None

    # Rent to the owner is an ordinary cost — unlike the Tilgung, none of it
    # comes back — so it is subtracted from both.
    cashflow = rent_f - costs_f - to_owner - inst
    operating = (rent_f - costs_f - to_owner - int_f) if (known or not inst) else None
    annual_rent = rent_f * 12
    annual_net = (rent_f - costs_f - to_owner) * 12

    val = float(value) if value else None
    return {
        "rent_monthly": round(rent_f, 2),
        "costs_monthly": round(costs_f, 2),
        # Only a sublet has one; for an owned flat it is 0.
        "rent_to_owner_monthly": round(to_owner, 2),
        "instalment_monthly": round(inst, 2),
        "interest_monthly": round(int_f, 2) if known else None,
        "principal_monthly": round(principal, 2) if known else None,
        # True when the loan's terms are on file, so interest and Tilgung are
        # the loan's own figures rather than an assumption.
        "split_known": bool(known or not inst),
        # What the account sees. Negative means the flat is fed each month.
        "cashflow_monthly": round(cashflow, 2),
        # Rent less costs less interest: the Tilgung is saving, not spending.
        "operating_monthly": round(operating, 2) if operating is not None else None,
        "annual_rent": round(annual_rent, 2),
        "annual_net": round(annual_net, 2),
        # Return on what the flat is worth, gross and after running costs.
        "gross_yield": round(annual_rent / val * 100, 2) if val else None,
        "net_yield": round(annual_net / val * 100, 2) if val else None,
        # The price-to-rent multiple German buyers quote. Lower is cheaper.
        "kaufpreisfaktor": round(val / annual_rent, 1) if val and annual_rent else None,
        # Return on the equity actually tied up, counting the Tilgung as the
        # saving it is. The figure landlords mean by "what is it earning me".
        "equity_return": (round((operating + principal) * 12 / (val - float(debt or 0)) * 100, 2)
                          if val and known and operating is not None
                          and (val - float(debt or 0)) > 0 else None),
        "rooms": rooms,
        "let_rooms": let_rooms,
        "vacant_rooms": max(rooms - let_rooms, 0),
        "occupancy": round(let_rooms / rooms * 100, 1) if rooms else None,
        "arrears": round(float(arrears or 0), 2),
    }


def portfolio_summary(flats):
    """The same figures across the flats handed in.

    Yields are computed from the summed value and rent, not averaged over the
    flats: an average of percentages weights a studio the same as a house.
    """
    if not flats:
        return None
    rent = sum(f["rent_monthly"] for f in flats)
    costs = sum(f["costs_monthly"] for f in flats)
    to_owner = sum(f.get("rent_to_owner_monthly", 0) for f in flats)
    inst = sum(f["instalment_monthly"] for f in flats)
    # A flat whose loan terms are not on file contributes to the instalment but
    # not to the split. Its interest counts as nothing here rather than as a
    # guess, and `split_unknown` says how many flats that applies to — so the
    # operating total is read as the floor it is, not as exact.
    interest = sum(f["interest_monthly"] or 0 for f in flats)
    principal = sum(f["principal_monthly"] or 0 for f in flats)
    unknown = sum(1 for f in flats if not f.get("split_known", True))
    arrears = sum(f["arrears"] for f in flats)
    rooms = sum(f["rooms"] for f in flats)
    let_rooms = sum(f["let_rooms"] for f in flats)

    # Only the flats carrying a value can contribute to a yield, and mixing
    # them with those that cannot would quietly understate it.
    valued = [f for f in flats if f.get("value")]
    value = sum(f["value"] for f in valued) if valued else None
    valued_rent = sum(f["rent_monthly"] for f in valued) * 12 if valued else 0.0
    valued_net = sum(f["rent_monthly"] - f["costs_monthly"]
                     - f.get("rent_to_owner_monthly", 0) for f in valued) * 12 if valued else 0.0

    return {
        "flats": len(flats),
        "rent_monthly": round(rent, 2),
        "costs_monthly": round(costs, 2),
        "rent_to_owner_monthly": round(to_owner, 2),
        "instalment_monthly": round(inst, 2),
        "interest_monthly": round(interest, 2),
        "principal_monthly": round(principal, 2),
        "cashflow_monthly": round(rent - costs - to_owner - inst, 2),
        "operating_monthly": round(rent - costs - to_owner - interest, 2),
        "split_unknown": unknown,
        "arrears": round(arrears, 2),
        "rooms": rooms,
        "let_rooms": let_rooms,
        "occupancy": round(let_rooms / rooms * 100, 1) if rooms else None,
        "value": round(value, 2) if value else None,
        "valued_flats": len(valued),
        "gross_yield": round(valued_rent / value * 100, 2) if value else None,
        "net_yield": round(valued_net / value * 100, 2) if value else None,
    }


def sublet_summary(flats):
    """The flats rented from an owner and let on.

    A yield means nothing here — the value is somebody else's. What the
    arrangement earns is the margin: rent in, less the rent paid to the owner,
    less whatever running costs fall on the subletter.
    """
    if not flats:
        return None
    rent = sum(f["rent_monthly"] for f in flats)
    to_owner = sum(f.get("rent_to_owner_monthly", 0) for f in flats)
    costs = sum(f["costs_monthly"] for f in flats)
    rooms = sum(f["rooms"] for f in flats)
    let_rooms = sum(f["let_rooms"] for f in flats)
    margin = rent - to_owner - costs
    return {
        "flats": len(flats),
        "rent_monthly": round(rent, 2),
        "rent_to_owner_monthly": round(to_owner, 2),
        "costs_monthly": round(costs, 2),
        "margin_monthly": round(margin, 2),
        # What share of the rent taken in survives as margin. Negative when a
        # flat stands empty and the owner is still being paid.
        "margin_pct": round(margin / rent * 100, 1) if rent else None,
        "rooms": rooms,
        "let_rooms": let_rooms,
        "vacant_rooms": max(rooms - let_rooms, 0),
        "arrears": round(sum(f["arrears"] for f in flats), 2),
    }


# ── What the flat was bought with ────────────────────────────────────────────
# The Kaufpreis lives in property_tax_profiles, where the AfA already reads it,
# and the loans carry their original principal. Between them they say how much
# of the purchase was the landlord's own money — which is what an
# Eigenkapitalrendite is a return on.

def purchase_equity(purchase_price=None, purchase_costs=None, loans_original=None):
    """What went into the flat, and how much of it was equity.

    Returns None where the Kaufpreis is not on file: a return on an unknown
    investment is not worth guessing at.

    The Nebenkosten matter more than they look. Berlin's Grunderwerbsteuer,
    notary and Grundbuch come to roughly a tenth of the price, and a loan that
    covered them can exceed the purchase price on its own — which is why the
    equity here can legitimately be small, and why leaving the Nebenkosten
    blank makes it look like zero.
    """
    if not purchase_price:
        return None
    price = float(purchase_price)
    extra = float(purchase_costs or 0)
    borrowed = float(loans_original or 0)
    invested = price + extra
    return {
        "purchase_price": round(price, 2),
        "purchase_costs": round(extra, 2) if purchase_costs else None,
        "invested_total": round(invested, 2),
        "loans_original": round(borrowed, 2),
        "equity_invested": round(invested - borrowed, 2),
        # The share of the purchase that was borrowed. Over 100 % means the
        # loan covered the Nebenkosten too.
        "loan_to_price": round(borrowed / price * 100, 1) if price else None,
        # Said plainly, because it changes how every figure below reads.
        "costs_missing": not purchase_costs,
    }


def equity_return_on_investment(monthly_result, equity_invested):
    """Eigenkapitalrendite: a yearly result against the money put in.

    Two results are worth measuring this way and they answer different
    questions, so the numerator is the caller's choice:

    - the **operating result** (rent less running costs less interest) is what
      the flat earns, counting the Tilgung as the saving it is;
    - the **cashflow** (the same, less the whole instalment) is what reaches
      the account — lower wherever a loan is being repaid, and the figure that
      says whether a flat funds itself.

    None where the equity is unknown, zero or negative: a percentage return on
    nothing is not a number, and a flat bought entirely on credit is better
    described by its cashflow in euro.
    """
    if monthly_result is None or not equity_invested or equity_invested <= 0:
        return None
    return round(float(monthly_result) * 12 / float(equity_invested) * 100, 2)


def value_gain(current_value=None, purchase_price=None):
    """What the flat has gained since it was bought, in euro and per cent."""
    if not current_value or not purchase_price:
        return None
    gain = float(current_value) - float(purchase_price)
    return {"gain": round(gain, 2),
            "gain_pct": round(gain / float(purchase_price) * 100, 1)}


def portfolio_purchase(flats):
    """What the owned flats cost to buy, and what the equity in them earns.

    Only the flats whose Kaufpreis is on file contribute; the count is
    returned so a partial figure is never read as the whole portfolio.
    """
    have = [f for f in flats if f.get("purchase")]
    if not have:
        return None
    price = sum(f["purchase"]["purchase_price"] for f in have)
    invested = sum(f["purchase"]["invested_total"] for f in have)
    borrowed = sum(f["purchase"]["loans_original"] for f in have)
    equity = invested - borrowed
    operating = sum(f.get("operating_monthly") or 0 for f in have)
    cash = sum(f.get("cashflow_monthly") or 0 for f in have)
    gains = [f["value_gain"]["gain"] for f in have if f.get("value_gain")]
    return {
        "flats": len(have),
        "purchase_price": round(price, 2),
        "invested_total": round(invested, 2),
        "loans_original": round(borrowed, 2),
        "equity_invested": round(equity, 2),
        "loan_to_price": round(borrowed / price * 100, 1) if price else None,
        "equity_return_invested": equity_return_on_investment(operating, equity),
        # The same equity measured against what actually reaches the account.
        "cash_return_invested": equity_return_on_investment(cash, equity),
        "value_gain": round(sum(gains), 2) if len(gains) == len(have) else None,
        # True while any flat is missing its Kaufnebenkosten, which makes the
        # equity look smaller and the return on it larger than they are.
        "costs_missing": any(f["purchase"]["costs_missing"] for f in have),
    }
