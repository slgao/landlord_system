from pydantic import BaseModel
from typing import Optional


class PaymentIn(BaseModel):
    contract_id: int
    amount: float                              # EUR value that counts as income
    payment_date: str
    currency: str = "EUR"
    # Foreign tender note: what the tenant actually paid, if not in EUR.
    orig_amount: Optional[float] = None
    orig_currency: Optional[str] = None


class PaymentOut(BaseModel):
    id: int
    contract_id: int
    tenant_name: Optional[str] = None
    apartment_name: Optional[str] = None
    amount: float
    payment_date: str
    currency: str = "EUR"
    orig_amount: Optional[float] = None
    orig_currency: Optional[str] = None
