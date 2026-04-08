from pydantic import BaseModel
from typing import Optional


class ApartmentOut(BaseModel):
    id: int
    property_id: int
    property_name: Optional[str] = None
    name: str
    flat: Optional[str] = None
