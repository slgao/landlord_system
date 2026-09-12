from pydantic import BaseModel, Field
from typing import Optional

from api.schemas.common import OptIsoDate


class PropertyIn(BaseModel):
    name: str
    address: Optional[str] = None
    building_id: Optional[int] = None
    we_label: Optional[str] = None       # e.g. "WE 3" — the Wohnungseigentum unit
    mea: Optional[float] = None          # Miteigentumsanteil (display-only)
    # What the flat is worth now. Equity is value less debt, and only the
    # purchase price was on file — so equity was guesswork until this is set.
    market_value: Optional[float] = Field(default=None, ge=0)
    market_value_date: OptIsoDate = None   # when that estimate was made


class PropertyOut(PropertyIn):
    id: int
    building_name: Optional[str] = None  # convenience: the building's display name
