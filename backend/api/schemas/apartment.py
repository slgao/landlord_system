from pydantic import BaseModel, Field
from typing import Optional


class ApartmentIn(BaseModel):
    property_id: int
    name: str
    flat: str | None = None
    # Wohnfläche. Without it there is no €/m², so no comparison against the
    # Mietspiegel and no read on whether a flat could carry another room.
    size_sqm: Optional[float] = Field(default=None, gt=0, le=10000)


class ApartmentOut(BaseModel):
    id: int
    property_id: int
    property_name: Optional[str] = None
    name: str
    flat: Optional[str] = None
    size_sqm: Optional[float] = None
