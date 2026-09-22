from pydantic import BaseModel, model_validator
from typing import Literal, Optional

from api.schemas.common import IsoDate

# 'rent' is what the contract charges each month. 'nk_settlement' is money
# moving because of a Nebenkostenabrechnung: a Nachzahlung the tenant pays in,
# or a Guthaben you pay back (negative). They are kept apart because rent
# arrears, the Anlage V split and the balance sheet each treat them differently.
PaymentKind = Literal["rent", "nk_settlement"]


class PaymentIn(BaseModel):
    contract_id: int
    amount: float                              # EUR value that counts as income
    payment_date: IsoDate
    currency: str = "EUR"
    # Foreign tender note: what the tenant actually paid, if not in EUR.
    orig_amount: Optional[float] = None
    orig_currency: Optional[str] = None
    kind: PaymentKind = "rent"
    settlement_id: Optional[int] = None

    @model_validator(mode="after")
    def _consistent(self):
        if self.amount == 0:
            raise ValueError("amount must not be zero")
        # Only a settlement can go the other way. A negative rent payment
        # would read as the tenant owing more rent.
        if self.kind == "rent" and self.amount < 0:
            raise ValueError("a rent payment must be positive; a refund to the "
                             "tenant is an NK settlement payment")
        if self.kind == "rent" and self.settlement_id is not None:
            raise ValueError("only an NK settlement payment can be linked to a settlement")
        return self


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
    kind: PaymentKind = "rent"
    settlement_id: Optional[int] = None
