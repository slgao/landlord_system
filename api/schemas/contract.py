from pydantic import BaseModel
from typing import Optional


class ContractOut(BaseModel):
    id: int
    tenant_id: int
    tenant_name: Optional[str] = None
    apartment_id: int
    apartment_name: Optional[str] = None
    property_name: Optional[str] = None
    rent: float
    start_date: str
    end_date: Optional[str] = None
    terminated: bool
