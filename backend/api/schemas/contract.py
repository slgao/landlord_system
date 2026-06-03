from pydantic import BaseModel
from typing import Optional


class ContractIn(BaseModel):
    tenant_id: int
    apartment_id: int
    rent: float
    currency: str = "EUR"
    start_date: str
    end_date: Optional[str] = None
    kaution_amount: Optional[float] = None
    kaution_currency: str = "EUR"
    kaution_paid_date: Optional[str] = None
    kaution_returned_date: Optional[str] = None
    kaution_returned_amount: Optional[float] = None
    terminated: bool = False


class ContractOut(BaseModel):
    id: int
    tenant_id: int
    tenant_name: Optional[str] = None
    apartment_id: int
    apartment_name: Optional[str] = None
    property_name: Optional[str] = None
    rent: float
    currency: str = "EUR"
    start_date: str
    end_date: Optional[str] = None
    kaution_amount: Optional[float] = None
    kaution_currency: str = "EUR"
    kaution_paid_date: Optional[str] = None
    kaution_returned_date: Optional[str] = None
    kaution_returned_amount: Optional[float] = None
    terminated: bool = False
