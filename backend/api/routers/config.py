from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from db import get_config, set_config
from auth import require_auth

router = APIRouter(prefix="/config", tags=["Config"])

_KEYS = [
    "landlord_name", "landlord_address", "landlord_iban",
    "landlord_bank", "landlord_email",
]
_SMTP_KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_from"]


class ConfigOut(BaseModel):
    landlord_name: Optional[str] = None
    landlord_address: Optional[str] = None
    landlord_iban: Optional[str] = None
    landlord_bank: Optional[str] = None
    landlord_email: Optional[str] = None


class ConfigIn(BaseModel):
    landlord_name: Optional[str] = None
    landlord_address: Optional[str] = None
    landlord_iban: Optional[str] = None
    landlord_bank: Optional[str] = None
    landlord_email: Optional[str] = None


class SmtpConfigOut(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_password: Optional[str] = None


class SmtpConfigIn(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_password: Optional[str] = None


# get_config/set_config are owner-scoped via the request's owner context, which
# require_auth publishes; the owner dependency below guarantees it is set.

@router.get("/", response_model=ConfigOut)
def get_all_config(owner: int = Depends(require_auth)):
    return ConfigOut(**{k: get_config(k) for k in _KEYS})


@router.put("/", response_model=ConfigOut)
def update_config(body: ConfigIn, owner: int = Depends(require_auth)):
    for k in _KEYS:
        v = getattr(body, k)
        if v is not None:
            set_config(k, v)
    return ConfigOut(**{k: get_config(k) for k in _KEYS})


@router.get("/smtp", response_model=SmtpConfigOut)
def get_smtp_config(owner: int = Depends(require_auth)):
    from db import get_secret_config
    return SmtpConfigOut(**{k: get_config(k) for k in _SMTP_KEYS},
                         smtp_password=get_secret_config("smtp_password", ""))


@router.put("/smtp", response_model=SmtpConfigOut)
def update_smtp_config(body: SmtpConfigIn, owner: int = Depends(require_auth)):
    from db import set_secret_config
    for k in _SMTP_KEYS:
        v = getattr(body, k)
        if v is not None:
            set_config(k, v)
    if body.smtp_password is not None:
        set_secret_config("smtp_password", body.smtp_password)
    from db import get_secret_config
    return SmtpConfigOut(**{k: get_config(k) for k in _SMTP_KEYS},
                         smtp_password=get_secret_config("smtp_password", ""))
