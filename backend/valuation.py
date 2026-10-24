"""What a flat is worth, and how much of that is the ground under it.

A condo is valued by comparison (Vergleichswertverfahren): what similar flats
in the area actually sold for, per m² of living space. The Gutachterausschuss
Berlin derives those factors once a year from the real purchase cases — 9.779
of them for the 2024 sales, averaging 5.369 €/m² — and they are the only
defensible basis for a figure. So:

    estimate = living_sqm × comparable_per_sqm

The Bodenrichtwert does *not* value the flat. It values the land, and a flat
owns only a share of it. It earns its place here for two other reasons:

- It is the part that updates itself. The comparable is a once-a-year number
  the owner sets; the land value comes free from Berlin's open data every
  March, and its movement is a real signal about the location.
- Divided by the zone's Geschossflächenzahl it becomes a land value per m² of
  *floor* space, which is directly comparable with the €/m² the flat is valued
  at. That ratio is the share of the price that is location rather than
  building — 1.600/2,5 = 640 €/m² against a 5.400 €/m² flat is about 12 %.

Where the Grundstücksfläche and the Miteigentumsanteil are both known, the
flat's land share is exact (BRW × plot × MEA) and is reported instead of the
GFZ approximation.

Every figure returned says what it rests on. An estimate whose comparable was
typed by hand a year ago is not the same claim as a measured one, and the UI
has to be able to say so.
"""
from datetime import date


def land_per_floor_sqm(brw, gfz):
    """Land value per m² of floor space: BRW ÷ GFZ.

    The GFZ says how many m² of floor space a m² of land may carry, so this
    converts a land price into the land component of a floor price. Without a
    GFZ there is no conversion to make.
    """
    if brw is None or not gfz:
        return None
    return float(brw) / float(gfz)


def land_share(brw, plot_sqm, mea):
    """The flat's own slice of the land value: BRW × plot × MEA.

    `mea` is the Miteigentumsanteil. It is recorded either as a fraction of
    1000 (the usual '87/1000' on a Teilungserklärung) or already as a share;
    anything above 1 is read as per-mille of the plot.
    """
    if brw is None or not plot_sqm or not mea:
        return None
    share = float(mea)
    if share > 1:
        share = share / 1000.0
    if not 0 < share <= 1:
        return None
    return float(brw) * float(plot_sqm) * share


def value_property(*, living_sqm=None, comparable_per_sqm=None, market_value=None,
                   market_value_date=None, brw=None, gfz=None, stichtag=None,
                   plot_sqm=None, mea=None):
    """One property's value, and the provenance of it.

    `market_value` is the owner's own figure — an appraisal, or a real offer —
    and always wins: it is a fact about this flat, where the comparable is an
    average over a district. The estimate is still returned alongside, because
    seeing the two apart is how you notice the appraisal has gone stale.
    """
    land_floor = land_per_floor_sqm(brw, gfz)
    estimate = None
    if living_sqm and comparable_per_sqm:
        estimate = float(living_sqm) * float(comparable_per_sqm)

    own = float(market_value) if market_value not in (None, "") else None
    value = own if own is not None else estimate
    basis = ("own" if own is not None else ("comparable" if estimate is not None else None))

    share = land_share(brw, plot_sqm, mea)
    # Share of the value that is land, not building. The exact MEA computation
    # when it is available, otherwise the GFZ approximation per m².
    land_pct = None
    if value:
        if share is not None:
            land_pct = share / value * 100.0
        elif land_floor is not None and living_sqm:
            land_pct = land_floor * float(living_sqm) / value * 100.0

    return {
        "value": round(value, 2) if value is not None else None,
        "basis": basis,
        "value_date": (market_value_date if basis == "own" else stichtag),
        "estimate": round(estimate, 2) if estimate is not None else None,
        "own_value": round(own, 2) if own is not None else None,
        "per_sqm": (round(value / float(living_sqm), 2)
                    if value is not None and living_sqm else None),
        "brw": float(brw) if brw is not None else None,
        "gfz": float(gfz) if gfz is not None else None,
        "stichtag": stichtag,
        "land_per_floor_sqm": round(land_floor, 2) if land_floor is not None else None,
        "land_share": round(share, 2) if share is not None else None,
        "land_pct": round(land_pct, 1) if land_pct is not None else None,
        # An estimate is never a valuation. Anything not priced by the owner is
        # flagged so the UI never presents a district average as this flat's worth.
        "estimated": basis != "own",
        "missing": _missing(living_sqm, comparable_per_sqm, own),
    }


def _missing(living_sqm, comparable_per_sqm, own):
    """What has to be filled in before a value can be worked out at all."""
    if own is not None:
        return []
    gaps = []
    if not living_sqm:
        gaps.append("living_sqm")
    if not comparable_per_sqm:
        gaps.append("comparable_per_sqm")
    return gaps


def portfolio_totals(valuations, debts):
    """Value, debt and equity across the portfolio.

    Withheld unless *every* valued property has a figure: a total that silently
    omits the flats without one reads as the whole portfolio and understates it.
    The same rule the amortization endpoint already applies to market values.
    """
    values = [v.get("value") for v in valuations]
    if not values or any(v is None for v in values):
        return None
    total_value = sum(values)
    total_debt = sum(float(d or 0) for d in debts)
    return {
        "value": round(total_value, 2),
        "debt": round(total_debt, 2),
        "equity": round(total_value - total_debt, 2),
        "ltv": round(total_debt / total_value * 100, 1) if total_value else None,
        "estimated": any(v.get("estimated") for v in valuations),
        "as_of": str(date.today()),
    }
