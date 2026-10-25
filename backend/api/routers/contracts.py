from datetime import date as _date
from typing import Literal, Optional as _Opt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

import rent_periods
from db import fetch, execute, execute_returning
from auth import require_auth
from api.schemas.contract import ContractIn, ContractOut
from api.schemas.common import IsoDate, OptIsoDate, parse_iso_date

router = APIRouter(prefix="/contracts", tags=["Contracts"])


def _row(r) -> ContractOut:
    return ContractOut(
        id=r[0], tenant_id=r[1], tenant_name=r[2],
        apartment_id=r[3], apartment_name=r[4], property_name=r[5],
        rent=float(r[6]),
        currency=r[7] or "EUR",
        start_date=r[8],
        end_date=r[9] if r[9] and r[9] != "None" else None,
        kaution_amount=float(r[10]) if r[10] else None,
        kaution_currency=r[11] or "EUR",
        kaution_paid_date=r[12] if r[12] and r[12] != "None" else None,
        kaution_returned_date=r[13] if r[13] and r[13] != "None" else None,
        kaution_returned_amount=float(r[14]) if r[14] else None,
        terminated=bool(r[15]),
        nebenkosten_vorauszahlung=float(r[16]) if r[16] is not None else None,
        nk_mode=r[17] or "prepayment",
    )


# `rent` and the NK share are the tenancy's current agreed price, resolved
# here rather than read from the contract: the contract holds no rent any more
# (see the contract_rents migration). The two laterals are the same rule the
# reports use — the price in force today, and for a tenancy that has not begun
# yet, the price it starts at — in the same round trip as the contract itself.
_SELECT = """
    SELECT c.id, c.tenant_id, t.name, c.apartment_id, a.name, p.name,
           COALESCE(cur.rent, upcoming.rent, 0), COALESCE(c.currency,'EUR'),
           c.start_date, c.end_date,
           c.kaution_amount, COALESCE(c.kaution_currency,'EUR'),
           c.kaution_paid_date, c.kaution_returned_date, c.kaution_returned_amount,
           c.terminated,
           COALESCE(cur.nebenkosten_vorauszahlung, upcoming.nebenkosten_vorauszahlung),
           c.nk_mode
    FROM contracts c
    JOIN tenants    t ON t.id = c.tenant_id
    JOIN apartments a ON a.id = c.apartment_id
    JOIN properties p ON p.id = a.property_id
    LEFT JOIN LATERAL (
        SELECT r.rent, r.nebenkosten_vorauszahlung FROM contract_rents r
        WHERE r.contract_id = c.id
          AND (r.valid_from = '' OR r.valid_from <= CURRENT_DATE::TEXT)
        ORDER BY r.valid_from DESC LIMIT 1
    ) cur ON TRUE
    LEFT JOIN LATERAL (
        SELECT r.rent, r.nebenkosten_vorauszahlung FROM contract_rents r
        WHERE r.contract_id = c.id
        ORDER BY r.valid_from ASC LIMIT 1
    ) upcoming ON TRUE
"""


def _get(contract_id: int, owner: int):
    rows = fetch(f"{_SELECT} WHERE c.id=? AND c.owner_id=?", (contract_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    return rows[0]


def _assert_own(contract_id: int, owner: int):
    if not fetch("SELECT id FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner)):
        raise HTTPException(status_code=404, detail="Contract not found")


@router.get("/", response_model=list[ContractOut])
def list_contracts(active_only: bool = False, owner: int = Depends(require_auth)):
    where = "AND COALESCE(c.terminated, 0) = 0" if active_only else ""
    rows = fetch(f"{_SELECT} WHERE c.owner_id=? {where} ORDER BY c.start_date DESC", (owner,))
    return [_row(r) for r in rows]


# Specific paths must come before /{contract_id} to avoid being captured by it
@router.get("/tenant/{tenant_id}", response_model=list[ContractOut])
def contracts_for_tenant(tenant_id: int, owner: int = Depends(require_auth)):
    rows = fetch(f"{_SELECT} WHERE c.tenant_id=? AND c.owner_id=? ORDER BY c.start_date DESC",
                 (tenant_id, owner))
    return [_row(r) for r in rows]


@router.get("/kaution-overview", response_model=list)
def kaution_overview_top(owner: int = Depends(require_auth)):
    return kaution_overview(owner)


@router.get("/{contract_id}/occupancy")
def contract_occupancy(contract_id: int, owner: int = Depends(require_auth)):
    """Auto-detect how many persons the flat's utility costs are divided by.
    See the WG vs. single-household rule below."""
    row = fetch("SELECT apartment_id FROM contracts WHERE id=? AND owner_id=?",
                (contract_id, owner))
    if not row:
        raise HTTPException(status_code=404, detail="Contract not found")
    apartment_id = row[0][0]

    co = fetch("SELECT COUNT(*) FROM co_tenants WHERE contract_id=? AND owner_id=?",
               (contract_id, owner))
    co_count = int(co[0][0]) if co and co[0][0] else 0

    if co_count > 0:
        # Single household on one contract → main tenant covers the whole flat.
        auto_count = 1
    else:
        pf = fetch("""
            SELECT COUNT(DISTINCT c.tenant_id)
            FROM contracts c
            JOIN apartments a ON c.apartment_id = a.id
            WHERE c.owner_id = ?
              AND COALESCE(c.terminated, 0) = 0
              AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= date('now')::text)
              AND a.flat IS NOT NULL AND a.flat != ''
              AND a.property_id = (SELECT property_id FROM apartments WHERE id=?)
              AND a.flat = (SELECT flat FROM apartments WHERE id=?)
        """, (owner, apartment_id, apartment_id))
        auto_count = int(pf[0][0]) if pf and pf[0][0] else 1

    return {"auto_count": max(1, auto_count), "co_tenant_count": co_count}


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(contract_id: int, owner: int = Depends(require_auth)):
    return _row(_get(contract_id, owner))


# The rent obligation is always in EUR. A tenant may *transfer* in another
# currency — that is recorded per payment as orig_amount/orig_currency, a note
# alongside the EUR value that actually settles the debt (see payments.py).
# Letting the contract itself carry a foreign rent would break every place that
# compares rent against payments: detect_overdue would weigh e.g. a CNY rent
# against EUR receipts and dun the tenant for the exchange rate.
RENT_CURRENCY = "EUR"


def _refuse_duplicate(tenant_id: int, apartment_id: int, start_date: str, owner: int) -> None:
    """One tenancy per tenant, flat and start date.

    A contract saved twice — a retry, or the same term entered again — is not
    visible as a mistake afterwards: both rows look right, and every month
    they overlap is counted twice in the expected rent. A second term for the
    same tenant in the same flat starts on a different day, so this refuses
    only the duplicate."""
    dup = fetch("SELECT id FROM contracts WHERE tenant_id=? AND apartment_id=? "
                "AND start_date=? AND owner_id=?",
                (tenant_id, apartment_id, start_date, owner))
    if dup:
        raise HTTPException(409,
            f"This tenant already has a contract for this flat starting {start_date} "
            f"(#{dup[0][0]}). Edit that one, or start a new term from a later date.")


@router.post("/", response_model=ContractOut, status_code=201)
def create_contract(body: ContractIn, owner: int = Depends(require_auth)):
    if not fetch("SELECT id FROM tenants WHERE id=? AND owner_id=?", (body.tenant_id, owner)):
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not fetch("SELECT id FROM apartments WHERE id=? AND owner_id=?", (body.apartment_id, owner)):
        raise HTTPException(status_code=404, detail="Apartment not found")
    _refuse_duplicate(body.tenant_id, body.apartment_id, body.start_date, owner)
    new_id = execute_returning("""
        INSERT INTO contracts
          (tenant_id, apartment_id, rent, currency, start_date, end_date,
           kaution_amount, kaution_currency, kaution_paid_date,
           kaution_returned_date, kaution_returned_amount, terminated,
           nebenkosten_vorauszahlung, nk_mode, owner_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        RETURNING id
    """, (body.tenant_id, body.apartment_id, body.rent, RENT_CURRENCY,
          body.start_date, body.end_date or None,
          body.kaution_amount, body.kaution_currency,
          body.kaution_paid_date or None,
          body.kaution_returned_date or None,
          body.kaution_returned_amount,
          int(body.terminated), body.nebenkosten_vorauszahlung, body.nk_mode, owner))[0][0]
    # What the tenancy was signed at, from the day it starts. Every later
    # price is another period beside it, so raising the rent next year leaves
    # this one — and the months it covered — exactly as they are.
    execute("""
        INSERT INTO contract_rents
          (contract_id, valid_from, rent, nebenkosten_vorauszahlung, kind, owner_id)
        VALUES (?,?,?,?,'initial',?)
    """, (new_id, body.start_date, body.rent, body.nebenkosten_vorauszahlung, owner))
    return _row(_get(new_id, owner))


@router.put("/{contract_id}", response_model=ContractOut)
def update_contract(contract_id: int, body: ContractIn, owner: int = Depends(require_auth)):
    _assert_own(contract_id, owner)
    # Read before writing: moving the tenancy's start has to move the price it
    # was signed at with it (see _realign_first_period below).
    was = fetch("SELECT start_date FROM contracts WHERE id=? AND owner_id=?",
                (contract_id, owner))
    old_start = was[0][0] if was else None
    if not fetch("SELECT id FROM tenants WHERE id=? AND owner_id=?", (body.tenant_id, owner)):
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not fetch("SELECT id FROM apartments WHERE id=? AND owner_id=?", (body.apartment_id, owner)):
        raise HTTPException(status_code=404, detail="Apartment not found")
    # kaution_returned_date / kaution_returned_amount are NOT written here: they
    # are derived from the kaution_returns ledger (kaution._sync_contract_return)
    # and an edit of the contract must not make them drift from the rows behind
    # them. The fields stay in ContractIn for API compatibility and are ignored.
    execute("""
        UPDATE contracts SET
          tenant_id=?, apartment_id=?, currency=?,
          start_date=?, end_date=?,
          kaution_amount=?, kaution_currency=?, kaution_paid_date=?, terminated=?,
          nk_mode=?
        WHERE id=? AND owner_id=?
    """, (body.tenant_id, body.apartment_id, RENT_CURRENCY,
          body.start_date, body.end_date or None,
          body.kaution_amount, body.kaution_currency,
          body.kaution_paid_date or None,
          int(body.terminated), body.nk_mode,
          contract_id, owner))
    # Editing a contract corrects what is on file; it does not record a rent
    # increase. So the rent here rewrites the period in force today — the
    # typo it was entered with — and a raise goes through POST /rents, which
    # leaves the earlier months at the price that was actually owed.
    _realign_first_period(contract_id, old_start, body.start_date, owner)
    _correct_current_rent(contract_id, body.rent, body.nebenkosten_vorauszahlung,
                          body.start_date, owner)
    return _row(_get(contract_id, owner))


@router.post("/{contract_id}/terminate", response_model=ContractOut)
def terminate_contract(contract_id: int, end_date: str | None = None,
                       owner: int = Depends(require_auth)):
    rows = fetch("SELECT end_date FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    from datetime import date as _date
    existing = rows[0][0]
    existing = existing if (existing and str(existing) != "None") else None
    try:
        end_date = parse_iso_date(end_date)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"end_date {e}")
    if end_date:
        ed = end_date
    elif existing:
        ed = existing
    else:
        ed = str(_date.today())
    execute("UPDATE contracts SET terminated=1, end_date=? WHERE id=? AND owner_id=?",
            (ed, contract_id, owner))
    return _row(_get(contract_id, owner))


@router.post("/{contract_id}/reopen", response_model=ContractOut)
def reopen_contract(contract_id: int, owner: int = Depends(require_auth)):
    rows = fetch("SELECT end_date FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner))
    if not rows:
        raise HTTPException(status_code=404, detail="Contract not found")
    from datetime import date as _date
    existing = rows[0][0]
    existing = existing if (existing and str(existing) != "None") else None
    keep_end = False
    if existing:
        try:
            keep_end = _date.fromisoformat(existing) > _date.today()
        except ValueError:
            keep_end = False
    if keep_end:
        execute("UPDATE contracts SET terminated=0 WHERE id=? AND owner_id=?", (contract_id, owner))
    else:
        execute("UPDATE contracts SET terminated=0, end_date=NULL WHERE id=? AND owner_id=?",
                (contract_id, owner))
    return _row(_get(contract_id, owner))


from pydantic import BaseModel as _BM
from typing import Optional as _Opt

class KautionReturnIn(_BM):
    returned_date: IsoDate
    returned_amount: float


class RentSettleIn(_BM):
    settled_until: OptIsoDate = None   # ISO date, or null/empty to clear


class RenewIn(_BM):
    mode: str                       # "extend" | "new_term"
    end_date: OptIsoDate = None     # new end date; null/empty = open-ended
    start_date: OptIsoDate = None   # new_term only: start of the new contract
    rent: _Opt[float] = None        # new_term only: new rent (defaults to current)


@router.post("/{contract_id}/settle-rent")
def settle_rent(contract_id: int, body: RentSettleIn, owner: int = Depends(require_auth)):
    _assert_own(contract_id, owner)
    settled = (body.settled_until or "").strip() or None
    execute("UPDATE contracts SET rent_settled_until=? WHERE id=? AND owner_id=?",
            (settled, contract_id, owner))
    return {"contract_id": contract_id, "rent_settled_until": settled}


@router.post("/{contract_id}/kaution-return", response_model=ContractOut)
def mark_kaution_returned(contract_id: int, body: KautionReturnIn,
                          owner: int = Depends(require_auth)):
    """Record a repayment. Kept as a convenience wrapper over the returns ledger
    so the contract's derived kaution_returned_* can never be written directly
    and drift from the rows behind it."""
    from api.routers.kaution import KautionReturnIn as LedgerReturnIn, create_return
    _assert_own(contract_id, owner)
    create_return(LedgerReturnIn(contract_id=contract_id, date=body.returned_date,
                                 amount=body.returned_amount, note=None), owner=owner)
    return _row(_get(contract_id, owner))


@router.post("/{contract_id}/kaution-return/clear", response_model=ContractOut)
def clear_kaution_return(contract_id: int, owner: int = Depends(require_auth)):
    """Undo every recorded repayment on this deposit."""
    from api.routers.kaution import _sync_contract_return
    _assert_own(contract_id, owner)
    execute("DELETE FROM kaution_returns WHERE contract_id=? AND owner_id=?", (contract_id, owner))
    _sync_contract_return(contract_id, owner)
    return _row(_get(contract_id, owner))


@router.post("/{contract_id}/renew", response_model=ContractOut)
def renew_contract(contract_id: int, body: RenewIn, owner: int = Depends(require_auth)):
    """Extend a contract in place, or roll it into a new term.

    - mode="extend": move (or clear) the end date on the existing contract so the
      same tenancy simply continues; un-terminates it if it was terminated.
      Returns the updated contract.
    - mode="new_term": close the current contract the day before `start_date`
      and create a fresh contract for the same tenant + apartment with the new
      rent. The deposit stays on the original contract (the new one starts at 0)
      so it is never double-counted; the per-month expected-rent logic then uses
      the old rent for old months and the new rent from the new term onward.
      Returns the NEW contract.
    """
    old = _get(contract_id, owner)                      # 404s if not owned
    new_end = (body.end_date or "").strip() or None

    if body.mode == "extend":
        execute("UPDATE contracts SET end_date=?, terminated=0 WHERE id=? AND owner_id=?",
                (new_end, contract_id, owner))
        return _row(_get(contract_id, owner))

    if body.mode == "new_term":
        new_start = (body.start_date or "").strip()
        if not new_start:
            raise HTTPException(status_code=400, detail="A start date is required for a new term")
        from datetime import date, timedelta
        try:
            old_end = (date.fromisoformat(new_start) - timedelta(days=1)).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start date (expected YYYY-MM-DD)")
        new_rent = body.rent if body.rent is not None else float(old[6])
        # The new term has to begin after the old one did, or closing the old
        # term "the day before" would give it an end date before its start.
        if new_start <= str(old[8]):
            raise HTTPException(status_code=400,
                                detail="The new term must start after the current term began")
        if new_end and new_end < new_start:
            raise HTTPException(status_code=400,
                                detail="The new end date must not be before the new start date")
        # Close the old term the day before the new one begins.
        execute("UPDATE contracts SET end_date=? WHERE id=? AND owner_id=?",
                (old_end, contract_id, owner))
        # Clone tenant/apartment into a new term; deposit carries over (0). The
        # rent currency is not cloned — it is EUR by the rule above, so a legacy
        # row with a foreign currency does not propagate it into a fresh term.
        # The utilities split carries over: the same flat with the same bills,
        # so losing it would silently turn the new term's rent warm and skew
        # every €/m² and the Anlage V income split with it.
        new_id = execute_returning("""
            INSERT INTO contracts
              (tenant_id, apartment_id, rent, currency, start_date, end_date,
               kaution_amount, kaution_currency, kaution_paid_date,
               kaution_returned_date, kaution_returned_amount, terminated,
               nebenkosten_vorauszahlung, nk_mode, owner_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            RETURNING id
        """, (old[1], old[3], new_rent, RENT_CURRENCY,
              new_start, new_end,
              0, old[11] or "EUR", None,
              None, None, 0, old[16], old[17] or "prepayment", owner))[0][0]
        # The new term's own first price. A new term is a new tenancy, so its
        # prices start here; the old term keeps every period it was charged at.
        execute("""
            INSERT INTO contract_rents
              (contract_id, valid_from, rent, nebenkosten_vorauszahlung, kind, owner_id)
            VALUES (?,?,?,?,'initial',?)
        """, (new_id, new_start, new_rent, old[16], owner))
        return _row(_get(new_id, owner))

    raise HTTPException(status_code=400, detail="mode must be 'extend' or 'new_term'")


def kaution_overview(owner: int):
    """Deposit ledger summary per contract. Served by kaution_overview_top,
    which is registered above /{contract_id} so the literal path wins."""
    rows = fetch("""
        SELECT c.id, t.name, a.name, p.name,
               c.kaution_amount, COALESCE(c.kaution_currency,'EUR'),
               c.kaution_paid_date, c.kaution_returned_date, c.kaution_returned_amount,
               COALESCE((SELECT SUM(amount) FROM kaution_deductions WHERE contract_id=c.id), 0),
               COALESCE((SELECT SUM(amount) FROM kaution_payments WHERE contract_id=c.id), 0),
               COALESCE((SELECT SUM(amount) FROM kaution_returns WHERE contract_id=c.id), 0),
               -- The Kaltmiete the tenancy started at: §551 caps the deposit at
               -- three of those, and it is the rent at signing that the cap is
               -- measured against, not whatever the rent has since become.
               (SELECT r.rent FROM contract_rents r WHERE r.contract_id = c.id
                ORDER BY r.valid_from ASC LIMIT 1),
               (SELECT r.nebenkosten_vorauszahlung FROM contract_rents r
                WHERE r.contract_id = c.id ORDER BY r.valid_from ASC LIMIT 1)
        FROM contracts c
        JOIN tenants t ON t.id=c.tenant_id
        JOIN apartments a ON a.id=c.apartment_id
        JOIN properties p ON p.id=a.property_id
        WHERE c.owner_id = ?
          AND c.kaution_amount IS NOT NULL AND c.kaution_amount > 0
        ORDER BY t.name
    """, (owner,))
    result = []
    for r in rows:
        k_amt = float(r[4]) if r[4] else 0.0
        deducted = float(r[9]) if r[9] else 0.0
        installments = float(r[10]) if r[10] else 0.0
        paid_date = r[6] and str(r[6]) != "None"
        legacy_fully_paid = installments == 0.0 and bool(paid_date)
        paid = k_amt if legacy_fully_paid else installments
        result.append({
            "contract_id": r[0], "tenant_name": r[1], "apartment_name": r[2],
            "property_name": r[3], "kaution_amount": k_amt,
            "kaution_currency": r[5], "kaution_paid_date": r[6],
            "kaution_returned_date": r[7],
            "kaution_returned_amount": float(r[8]) if r[8] else None,
            "deducted": deducted, "paid": paid,
            "outstanding": round(k_amt - paid, 2),
            "balance": round(k_amt - deducted, 2),
            "returned_total": round(float(r[11]) if r[11] else 0.0, 2),
            # What is still with the landlord: owed back, less what has gone back.
            "still_held": round(k_amt - deducted - (float(r[11]) if r[11] else 0.0), 2),
            **_kaution_cap_note(k_amt, r[12], r[13]),
        })
    return result


def _kaution_cap_note(agreed: float, first_rent, first_nkv) -> dict:
    """What §551 Abs. 1 BGB allows, and whether this deposit exceeds it.

    Three Kaltmieten — the rent without the Nebenkosten prepayment. A deposit
    agreed above the cap is not void; the excess is simply not owed and the
    tenant can reclaim it at any time, which is worth knowing before they ask
    rather than after. Without a Kaltmiete on file there is nothing to measure
    against, and saying nothing is better than guessing.
    """
    if first_rent is None:
        return {"kaution_cap": None, "kaution_over_cap": None}
    cold = rent_periods.cold_rent(first_rent, first_nkv or 0)
    cap = float(rent_periods.kaution_cap(cold))
    over = round(agreed - cap, 2)
    return {"kaution_cap": cap, "kaution_over_cap": over if over > 0.005 else None}


@router.delete("/{contract_id}", status_code=204)
def delete_contract(contract_id: int, owner: int = Depends(require_auth)):
    _assert_own(contract_id, owner)
    # Child rows (payments, kaution_*, co_tenants, reminders) cascade via FKs.
    execute("DELETE FROM contracts WHERE id=? AND owner_id=?", (contract_id, owner))


# ── The agreed rent, period by period ────────────────────────────────────────

class RentPeriodIn(BaseModel):
    """A price and the day it starts applying."""
    valid_from: IsoDate
    rent: float = Field(ge=0)
    nebenkosten_vorauszahlung: _Opt[float] = Field(default=None, ge=0)
    kind: Literal["initial", "agreed", "staffel", "index", "modernisation"] = "agreed"
    note: _Opt[str] = None

    @model_validator(mode="after")
    def _nk_inside_rent(self):
        if (self.nebenkosten_vorauszahlung or 0) > self.rent:
            raise ValueError("the Nebenkosten share cannot be larger than the rent")
        return self


class RentCheck(BaseModel):
    """Something about an increase that is worth a second look. Never a
    refusal: every rule here has lawful exceptions, and a tool that blocked
    the entry would simply be wrong about somebody's tenancy."""
    code: str
    paragraph: str = ""
    message: str
    over_general: bool = False


class RentPeriodsOut(BaseModel):
    periods: list["RentPeriodOut"]
    checks: list[RentCheck] = []


class RentPeriodOut(BaseModel):
    id: int
    contract_id: int
    valid_from: str
    rent: float
    nebenkosten_vorauszahlung: _Opt[float] = None
    cold_rent: float
    kind: str
    kind_label: str
    note: _Opt[str] = None
    current: bool


_RENTS_SELECT = """
    SELECT id, contract_id, valid_from, rent, nebenkosten_vorauszahlung, kind, note
    FROM contract_rents
"""


def _rent_row(r, today: str) -> RentPeriodOut:
    nkv = float(r[4]) if r[4] is not None else None
    return RentPeriodOut(
        id=r[0], contract_id=r[1], valid_from=r[2] or "", rent=float(r[3]),
        nebenkosten_vorauszahlung=nkv,
        cold_rent=float(rent_periods.cold_rent(r[3], r[4] or 0)),
        kind=r[5] or "agreed",
        kind_label=rent_periods.KIND_LABELS.get(r[5] or "agreed", ""),
        note=r[6], current=False,
    )


def _rent_periods(contract_id: int, owner: int) -> list[RentPeriodOut]:
    rows = fetch(f"{_RENTS_SELECT} WHERE contract_id=? AND owner_id=? ORDER BY valid_from",
                 (contract_id, owner))
    today = _date.today().isoformat()
    out = [_rent_row(r, today) for r in rows]
    # Exactly one period is the one being charged now: the last that has
    # started, or — for a tenancy that has not begun — the one it starts at.
    started = [p for p in out if not p.valid_from or p.valid_from <= today]
    current = started[-1] if started else (out[0] if out else None)
    if current is not None:
        current.current = True
    return out


def _realign_first_period(contract_id: int, old_start, new_start, owner: int) -> None:
    """Move the price a tenancy was signed at when its start date is corrected.

    Correcting a start date is ordinary — a typo, or a handover that slipped a
    week. Leaving the first price on the old date strands it before the
    tenancy, and then no new price can be recorded before that date either,
    because a price may not start before the tenancy does. So the period that
    began when the tenancy did moves with it.

    Only that one. A later increase was agreed for its own date and has
    nothing to do with when the tenancy began.
    """
    old_start = _clean_date(old_start)
    new_start = _clean_date(new_start)
    if not old_start or not new_start or old_start == new_start:
        return
    first = fetch("SELECT id, valid_from FROM contract_rents "
                  "WHERE contract_id=? AND owner_id=? ORDER BY valid_from LIMIT 1",
                  (contract_id, owner))
    if not first or _clean_date(first[0][1]) != old_start:
        return                      # not the signing price: leave it alone
    clash = fetch("SELECT id FROM contract_rents WHERE contract_id=? AND valid_from=? "
                  "AND id<>? AND owner_id=?",
                  (contract_id, new_start, first[0][0], owner))
    if clash:
        return                      # a price already starts there; nothing to move
    execute("UPDATE contract_rents SET valid_from=? WHERE id=? AND owner_id=?",
            (new_start, first[0][0], owner))


def _clean_date(v):
    return None if v is None or str(v) in ("None", "") else str(v)


def _correct_current_rent(contract_id: int, rent, nkv, start_date, owner: int) -> None:
    """Rewrite the price in force today, or write the first one if a tenancy
    somehow has none (a contract created before this table existed)."""
    periods = _rent_periods(contract_id, owner)
    current = next((p for p in periods if p.current), None)
    if current is None:
        execute("""
            INSERT INTO contract_rents
              (contract_id, valid_from, rent, nebenkosten_vorauszahlung, kind, owner_id)
            VALUES (?,?,?,?,'initial',?)
        """, (contract_id, start_date, rent, nkv, owner))
        return
    execute("""
        UPDATE contract_rents SET rent=?, nebenkosten_vorauszahlung=?
        WHERE id=? AND owner_id=?
    """, (rent, nkv, current.id, owner))


@router.get("/{contract_id}/rents", response_model=RentPeriodsOut)
def list_rent_periods(contract_id: int, owner: int = Depends(require_auth)):
    """Every price this tenancy has been charged at, oldest first."""
    _assert_own(contract_id, owner)
    return RentPeriodsOut(periods=_rent_periods(contract_id, owner))


@router.post("/{contract_id}/rents", response_model=RentPeriodsOut, status_code=201)
def add_rent_period(contract_id: int, body: RentPeriodIn,
                    owner: int = Depends(require_auth)):
    """Record what the rent becomes, and from when.

    The earlier price stays exactly as it is, and with it every month it
    covered: this is how a §558 increase, a Staffel step or an Indexmiete
    adjustment is entered without restating a year that has already been
    filed. Dating it ahead is normal — an increase is owed from the beginning
    of the third calendar month after the demand reaches the tenant, and a
    Staffelmiete's steps are agreed years before they are charged.
    """
    _assert_own(contract_id, owner)
    row = fetch("SELECT start_date, end_date FROM contracts WHERE id=? AND owner_id=?",
                (contract_id, owner))[0]
    start, end = row[0], row[1]
    if start and str(start) not in ("None", "") and body.valid_from < str(start):
        raise HTTPException(422, f"The tenancy starts on {start}; a price cannot "
                                 f"apply before it.")
    if end and str(end) not in ("None", "") and body.valid_from > str(end):
        raise HTTPException(422, f"The tenancy ended on {end}; a price starting "
                                 f"after that would never be charged.")
    if fetch("SELECT id FROM contract_rents WHERE contract_id=? AND valid_from=? "
             "AND owner_id=?", (contract_id, body.valid_from, owner)):
        raise HTTPException(409, f"This tenancy already has a price starting on "
                                 f"{body.valid_from}. Edit that one instead.")
    # An increase that says nothing about the Nebenkosten keeps the share
    # already agreed: raising the rent does not silently turn the rent warm,
    # which would move the Kaltmiete, every €/m² derived from it and the
    # Umlagen line of the Anlage V. Pass 0 to say there is no share.
    before = rent_periods.RentSchedule(
        [(p.valid_from, p.rent, p.nebenkosten_vorauszahlung)
         for p in _rent_periods(contract_id, owner)])
    nkv = body.nebenkosten_vorauszahlung
    if nkv is None:
        current = next((p for p in _rent_periods(contract_id, owner) if p.current), None)
        nkv = current.nebenkosten_vorauszahlung if current else None
        if nkv is not None and nkv > body.rent:
            raise HTTPException(422, f"The Nebenkosten share carried over "
                                     f"({nkv:.2f} €) is larger than the new rent.")
    execute("""
        INSERT INTO contract_rents
          (contract_id, valid_from, rent, nebenkosten_vorauszahlung, kind, note, owner_id)
        VALUES (?,?,?,?,?,?,?)
    """, (contract_id, body.valid_from, body.rent, nkv,
          body.kind, body.note or None, owner))
    # Measured against the prices as they were *before* this one, which is
    # what §558 compares: the rent three years ago and the date of the last
    # increase.
    checks = rent_periods.check_increase(before, body.valid_from, body.rent, body.kind)
    return RentPeriodsOut(periods=_rent_periods(contract_id, owner),
                          checks=[RentCheck(**c) for c in checks])


@router.put("/{contract_id}/rents/{period_id}", response_model=RentPeriodsOut)
def update_rent_period(contract_id: int, period_id: int, body: RentPeriodIn,
                       owner: int = Depends(require_auth)):
    """Correct a price that was entered wrongly."""
    _assert_own(contract_id, owner)
    if not fetch("SELECT id FROM contract_rents WHERE id=? AND contract_id=? AND owner_id=?",
                 (period_id, contract_id, owner)):
        raise HTTPException(404, "Rent period not found")
    if fetch("SELECT id FROM contract_rents WHERE contract_id=? AND valid_from=? "
             "AND id<>? AND owner_id=?", (contract_id, body.valid_from, period_id, owner)):
        raise HTTPException(409, f"Another price already starts on {body.valid_from}.")
    execute("""
        UPDATE contract_rents
        SET valid_from=?, rent=?, nebenkosten_vorauszahlung=?, kind=?, note=?
        WHERE id=? AND owner_id=?
    """, (body.valid_from, body.rent, body.nebenkosten_vorauszahlung, body.kind,
          body.note or None, period_id, owner))
    return RentPeriodsOut(periods=_rent_periods(contract_id, owner))


@router.delete("/{contract_id}/rents/{period_id}", response_model=RentPeriodsOut)
def delete_rent_period(contract_id: int, period_id: int,
                       owner: int = Depends(require_auth)):
    """Remove a price that should not have been recorded.

    The last one cannot go: a tenancy with no price at all would be expected
    to earn nothing, in every month it ever ran.
    """
    _assert_own(contract_id, owner)
    periods = _rent_periods(contract_id, owner)
    if not any(p.id == period_id for p in periods):
        raise HTTPException(404, "Rent period not found")
    if len(periods) == 1:
        raise HTTPException(409, "This is the only price on file for the tenancy. "
                                 "Edit it instead of removing it.")
    execute("DELETE FROM contract_rents WHERE id=? AND owner_id=?", (period_id, owner))
    return RentPeriodsOut(periods=_rent_periods(contract_id, owner))
