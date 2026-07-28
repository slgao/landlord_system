from pydantic import BaseModel
from typing import Optional


class BuildingIn(BaseModel):
    name: Optional[str] = None
    street: Optional[str] = None
    house_no: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    notes: Optional[str] = None


class BuildingOut(BuildingIn):
    id: int
    unit_count: int = 0  # number of WEs (properties) under this building
