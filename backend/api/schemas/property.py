from pydantic import BaseModel
from typing import Optional


class PropertyIn(BaseModel):
    name: str
    address: Optional[str] = None
    building_id: Optional[int] = None
    we_label: Optional[str] = None       # e.g. "WE 3" — the Wohnungseigentum unit
    mea: Optional[float] = None          # Miteigentumsanteil (display-only)


class PropertyOut(PropertyIn):
    id: int
    building_name: Optional[str] = None  # convenience: the building's display name
