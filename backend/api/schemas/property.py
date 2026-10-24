from pydantic import BaseModel, Field
from typing import Optional

from api.schemas.common import OptIsoDate


class PropertyIn(BaseModel):
    name: str
    address: Optional[str] = None
    building_id: Optional[int] = None
    we_label: Optional[str] = None       # e.g. "WE 3" — the Wohnungseigentum unit
    mea: Optional[float] = None          # Miteigentumsanteil (display-only)
    # Whether this flat is yours. A managed-but-not-owned flat is tracked like
    # any other — rent, meters, Nebenkosten — but its worth is not your asset,
    # so it stays out of the portfolio value, the equity and the LTV.
    owned: bool = True
    # What the flat is worth now. Equity is value less debt, and only the
    # purchase price was on file — so equity was guesswork until this is set.
    market_value: Optional[float] = Field(default=None, ge=0)
    market_value_date: OptIsoDate = None   # when that estimate was made
    # The unit's Wohnfläche. Not summed from its apartments: a WG's rooms do
    # not add up to the flat's area, hallway, kitchen and bath belonging to
    # none of them.
    living_sqm: Optional[float] = Field(default=None, ge=0)
    plot_sqm: Optional[float] = Field(default=None, ge=0)     # Grundstücksfläche
    # € per m² of living space for comparable flats — what actually values a
    # condo. The Gutachterausschuss publishes these per district yearly.
    comparable_per_sqm: Optional[float] = Field(default=None, ge=0)
    valuation_note: Optional[str] = None   # where that comparable came from


class PropertyOut(PropertyIn):
    id: int
    building_name: Optional[str] = None  # convenience: the building's display name
