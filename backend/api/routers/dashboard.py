from datetime import date
from fastapi import APIRouter, Depends
from db import fetch
from auth import require_auth

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
def stats(owner: int = Depends(require_auth)):
    return {
        "properties": fetch("SELECT COUNT(*) FROM properties WHERE owner_id=?", (owner,))[0][0],
        "apartments":  fetch("SELECT COUNT(*) FROM apartments WHERE owner_id=?", (owner,))[0][0],
        "tenants":     fetch("SELECT COUNT(*) FROM tenants WHERE owner_id=?", (owner,))[0][0],
        "contracts":   fetch("SELECT COUNT(*) FROM contracts WHERE owner_id=? "
                             "AND COALESCE(terminated,0)=0", (owner,))[0][0],
    }


@router.get("/alerts")
def alerts(owner: int = Depends(require_auth)):
    rows = fetch("""
        SELECT t.name, a.name, p.name, c.end_date
        FROM contracts c
        JOIN tenants    t ON c.tenant_id    = t.id
        JOIN apartments a ON c.apartment_id = a.id
        JOIN properties p ON a.property_id  = p.id
        WHERE c.owner_id = ?
          AND c.end_date IS NOT NULL AND c.end_date != 'None'
          AND COALESCE(c.terminated, 0) = 0
        ORDER BY c.end_date
    """, (owner,))
    today = date.today()
    result = []
    for tenant_name, apt_name, prop_name, end_str in rows:
        try:
            end = date.fromisoformat(end_str)
            days = (end - today).days
            if days < 0:
                level = "expired"
            elif days <= 90:
                level = "warning"
            else:
                continue
            result.append({
                "tenant_name":    tenant_name,
                "apartment_name": apt_name,
                "property_name":  prop_name,
                "end_date":       end_str,
                "days_remaining": days,
                "level":          level,
            })
        except ValueError:
            continue
    return result
