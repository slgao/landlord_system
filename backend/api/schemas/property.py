from pydantic import BaseModel
from typing import Optional


class PropertyIn(BaseModel):
    name: str
    address: Optional[str] = None


class PropertyOut(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
