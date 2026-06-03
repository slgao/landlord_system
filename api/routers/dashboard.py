from datetime import date
from fastapi import APIRouter
from db import fetch

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
def stats():
    return {
        "properties": fetch("SELECT COUNT(*) FROM properties")[0][0],
        "apartments":  fetch("SELECT COUNT(*) FROM apartments")[0][0],
        "tenants":     fetch("SELECT COUNT(*) FROM tenants")[0][0],
        "contracts":   fetch("SELECT COUNT(*) FROM contracts WHERE COALESCE(terminated,0)=0")[0][0],
    }


@router.get("/alerts")
def alerts():
    rows = fetch("""
        SELECT t.name, a.name, p.name, c.end_date
        FROM contracts c
        JOIN tenants    t ON c.tenant_id    = t.id
        JOIN apartments a ON c.apartment_id = a.id
        JOIN properties p ON a.property_id  = p.id
        WHERE c.end_date IS NOT NULL AND c.end_date != 'None'
          AND COALESCE(c.terminated, 0) = 0
        ORDER BY c.end_date
    """)
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
