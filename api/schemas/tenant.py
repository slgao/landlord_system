from pydantic import BaseModel
from typing import Optional


class TenantIn(BaseModel):
    name: str
    email: Optional[str] = None
    gender: str = "diverse"


class TenantOut(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    gender: str
