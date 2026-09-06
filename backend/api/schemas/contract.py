from pydantic import BaseModel, Field, model_validator
from typing import Optional

from api.schemas.common import IsoDate, OptIsoDate


class ContractIn(BaseModel):
    tenant_id: int
    apartment_id: int
    rent: float = Field(ge=0)
    currency: str = "EUR"
    start_date: IsoDate
    end_date: OptIsoDate = None
    kaution_amount: Optional[float] = Field(default=None, ge=0)
    kaution_currency: str = "EUR"
    kaution_paid_date: OptIsoDate = None
    kaution_returned_date: OptIsoDate = None
    kaution_returned_amount: Optional[float] = None
    terminated: bool = False

    @model_validator(mode="after")
    def _end_after_start(self):
        # A contract that ends before it begins is a typo, never a tenancy —
        # and the balance sheet would count it for no month at all.
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


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
