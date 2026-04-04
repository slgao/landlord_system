import streamlit as st
from datetime import date
from db import fetch


def show():
    st.header("Property Dashboard")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Properties", fetch("SELECT COUNT(*) FROM properties")[0][0])
    col2.metric("Apartments", fetch("SELECT COUNT(*) FROM apartments")[0][0])
    col3.metric("Tenants",    fetch("SELECT COUNT(*) FROM tenants")[0][0])
    col4.metric("Contracts",  fetch("SELECT COUNT(*) FROM contracts")[0][0])

    st.divider()
    st.subheader("Contract Alerts")

    upcoming = fetch("""
        SELECT t.name, a.name, c.end_date
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        WHERE c.end_date IS NOT NULL AND c.end_date != 'None'
        ORDER BY c.end_date
    """)

    today = date.today()
    alerts = False
    for t_name, a_name, end_str in upcoming:
        try:
            end = date.fromisoformat(end_str)
            days = (end - today).days
            if days < 0:
                st.error(f"**{t_name}** ({a_name}) — EXPIRED on {end.strftime('%d.%m.%Y')}")
                alerts = True
            elif days <= 90:
                st.warning(f"**{t_name}** ({a_name}) — Expires in {days} days ({end.strftime('%d.%m.%Y')})")
                alerts = True
        except ValueError:
            continue

    if not alerts:
        st.success("No contracts expiring in the next 90 days.")
