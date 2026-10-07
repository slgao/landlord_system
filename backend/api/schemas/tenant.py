from pydantic import BaseModel
from typing import Optional


class TenantIn(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: str = "diverse"


class TenantOut(BaseModel):
    # How many contracts this tenant has running today — started, not ended,
    # not terminated. A signed contract that starts next month does not count:
    # nobody is renting on it yet.
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: str
    active_contracts: int = 0
    # One entry per contract running today: which flat, in which property.
    renting: list[dict] = []
