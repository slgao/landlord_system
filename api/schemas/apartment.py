from pydantic import BaseModel
from typing import Optional


class ApartmentIn(BaseModel):
    property_id: int
    name: str
    flat: str | None = None


class ApartmentOut(BaseModel):
    id: int
    property_id: int
    property_name: Optional[str] = None
    name: str
    flat: Optional[str] = None
