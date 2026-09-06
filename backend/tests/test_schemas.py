"""The shared date validators: every date column is TEXT and every consumer
trusts YYYY-MM-DD, so the request schemas have to refuse anything else."""
import pytest
from pydantic import ValidationError

from api.schemas.common import parse_iso_date
from api.schemas.contract import ContractIn
from api.schemas.payment import PaymentIn
from api.routers.flat_costs import FlatCostIn
from api.routers.contracts import RentSettleIn


def _contract(**kw):
    base = dict(tenant_id=1, apartment_id=1, rent=500, start_date="2026-01-01")
    base.update(kw)
    return ContractIn(**base)


def test_required_date_rejects_blank_and_garbage():
    for bad in ("", "None", "2026-13-01", "01.02.2026", "2026-1-1", None):
        with pytest.raises(ValidationError):
            _contract(start_date=bad)


def test_optional_date_blank_means_none():
    c = _contract(end_date="", kaution_paid_date="None", kaution_returned_date=None)
    assert c.end_date is None and c.kaution_paid_date is None


def test_datetime_prefix_is_trimmed_to_the_day():
    assert _contract(start_date="2026-01-01T00:00:00").start_date == "2026-01-01"


def test_end_before_start_is_rejected():
    with pytest.raises(ValidationError):
        _contract(end_date="2025-12-31")
    assert _contract(end_date="2026-01-01").end_date == "2026-01-01"   # same day is fine


def test_negative_rent_and_deposit_are_rejected():
    with pytest.raises(ValidationError):
        _contract(rent=-1)
    with pytest.raises(ValidationError):
        _contract(kaution_amount=-0.01)


def test_payment_date_is_validated():
    with pytest.raises(ValidationError):
        PaymentIn(contract_id=1, amount=10, payment_date="")
    assert PaymentIn(contract_id=1, amount=10, payment_date="2026-05-05").payment_date == "2026-05-05"


def test_flat_cost_window_order_and_blank_type():
    with pytest.raises(ValidationError):
        FlatCostIn(apartment_id=1, cost_type="Hausgeld", amount=1,
                   valid_from="2026-02-01", valid_to="2026-01-01")
    with pytest.raises(ValidationError):
        FlatCostIn(apartment_id=1, cost_type="", amount=1)
    fc = FlatCostIn(apartment_id=1, cost_type="Hausgeld", amount=1, valid_from="", valid_to=None)
    assert fc.valid_from is None and fc.valid_to is None


def test_settle_until_clears_on_blank():
    assert RentSettleIn(settled_until="").settled_until is None
    with pytest.raises(ValidationError):
        RentSettleIn(settled_until="soon")


def test_parse_iso_date_for_query_params():
    assert parse_iso_date(None) is None
    assert parse_iso_date("") is None
    assert parse_iso_date("2026-03-04") == "2026-03-04"
    with pytest.raises(ValueError):
        parse_iso_date("2026/03/04")
