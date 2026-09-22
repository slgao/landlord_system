"""What a Kaution deduction means for the rest of the books.

A deduction is part of the deposit kept back instead of paid out. Most kinds
are money the landlord receives at that moment (§11 EStG: the offset is the
Zufluss), so they have to show up where that money would:

- NK_CATEGORY — a Nebenkosten Nachzahlung. Umlagen; settles an NK
  Abrechnung (see api/routers/nk_settlements.py).
- RENT_ARREARS — rent the tenant did not pay, taken from the deposit.
- RENT_AGREED — rent you agreed the tenant could "abwohnen" from the deposit
  instead of paying it.

The two rent kinds are the same money — rent received on the deduction date,
counting against rent owed — and differ only in what happened, which is why
they are separate categories rather than one: a Mietrückstand is a tenant
who did not pay, an agreed Abwohnen is not.

Damages, cleaning and the like are not rent and are left alone here.
"""

NK_CATEGORY = "NK Nachzahlung"
NK_REF_TYPE = "nk_settlement"

RENT_ARREARS = "Mietrückstand"
RENT_AGREED = "Abwohnen (vereinbart)"
RENT_CATEGORIES = (RENT_ARREARS, RENT_AGREED)
