from datetime import date
from fastapi import APIRouter, Depends
from db import fetch
from auth import require_auth

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
def stats(owner: int = Depends(require_auth)):
    # A contract signed ahead of the move-in is not running yet, so it is
    # counted separately instead of inflating the "active" number.
    today = date.today().isoformat()
    # One round trip, not five. Every figure is a COUNT over a different table,
    # which is exactly what scalar subqueries are for — and on a database 38 ms
    # away four saved round trips are most of the endpoint's latency.
    r = fetch("""
        SELECT (SELECT COUNT(*) FROM properties WHERE owner_id=?),
               (SELECT COUNT(*) FROM apartments WHERE owner_id=?),
               (SELECT COUNT(*) FROM tenants    WHERE owner_id=?),
               (SELECT COUNT(*) FROM contracts  WHERE owner_id=?
                  AND COALESCE(terminated,0)=0 AND start_date<=?),
               (SELECT COUNT(*) FROM contracts  WHERE owner_id=?
                  AND COALESCE(terminated,0)=0 AND start_date>?)
    """, (owner, owner, owner, owner, today, owner, today))[0]
    return {"properties": r[0], "apartments": r[1], "tenants": r[2],
            "contracts": r[3], "upcoming": r[4]}


@router.get("/alerts")
def alerts(owner: int = Depends(require_auth)):
    """Contracts that need attention within the next 90 days: ones running out,
    ones that already ran out unnoticed, and ones that are signed but have not
    started yet."""
    rows = fetch("""
        SELECT t.name, a.name, p.name, c.start_date, c.end_date
        FROM contracts c
        JOIN tenants    t ON c.tenant_id    = t.id
        JOIN apartments a ON c.apartment_id = a.id
        JOIN properties p ON a.property_id  = p.id
        WHERE c.owner_id = ?
          AND COALESCE(c.terminated, 0) = 0
    """, (owner,))
    today = date.today()
    result = []
    for tenant_name, apt_name, prop_name, start_str, end_str in rows:
        entry = {
            "tenant_name":    tenant_name,
            "apartment_name": apt_name,
            "property_name":  prop_name,
            "start_date":     start_str,
            "end_date":       end_str if end_str and end_str != "None" else None,
        }
        start = _parse(start_str)
        if start and start > today:
            days = (start - today).days
            if days <= 90:
                result.append({**entry, "days_remaining": days, "level": "upcoming"})
            continue                     # not started: it cannot be expiring
        end = _parse(entry["end_date"])
        if not end:
            continue
        days = (end - today).days
        if days < 0:
            result.append({**entry, "days_remaining": days, "level": "expired"})
        elif days <= 90:
            result.append({**entry, "days_remaining": days, "level": "warning"})
    # Most urgent first: what already lapsed, then what is running out, then
    # what is about to begin.
    order = {"expired": 0, "warning": 1, "upcoming": 2}
    result.sort(key=lambda r: (order[r["level"]], r["days_remaining"]))
    return result


def _parse(value) -> date | None:
    if not value or str(value) == "None":
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
