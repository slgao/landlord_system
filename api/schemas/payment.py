from pydantic import BaseModel
from typing import Optional


class PaymentIn(BaseModel):
    contract_id: int
    amount: float
    payment_date: str
    currency: str = "EUR"


class PaymentOut(BaseModel):
    id: int
    contract_id: int
    tenant_name: Optional[str] = None
    apartment_name: Optional[str] = None
    amount: float
    payment_date: str
    currency: str = "EUR"
