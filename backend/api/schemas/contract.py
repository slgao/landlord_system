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
    # The utilities portion of `rent`. Rent is what the tenant actually
    # transfers; how much of it is a Nebenkosten prepayment depends on the
    # contract. Kaltmiete = rent − this, and it is the Kaltmiete that €/m²
    # and any Mietspiegel comparison have to use — comparing a warm rent
    # against a cold one reads as a flat earning more than it does.
    nebenkosten_vorauszahlung: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _consistent(self):
        # A contract that ends before it begins is a typo, never a tenancy —
        # and the balance sheet would count it for no month at all.
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        # Utilities cannot exceed the whole rent; that would make Kaltmiete
        # negative and quietly poison every €/m² derived from it.
        if (self.nebenkosten_vorauszahlung is not None
                and self.nebenkosten_vorauszahlung > self.rent):
            raise ValueError("nebenkosten_vorauszahlung must not exceed the rent")
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
    nebenkosten_vorauszahlung: Optional[float] = None
