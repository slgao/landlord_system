import streamlit as st
import pandas as pd
from db import fetch
from logic import tenant_ledger
from currencies import sym, fmt


def show():
    st.header("Tenant Ledger")

    tenants = fetch("SELECT id, name FROM tenants")
    if not tenants:
        st.info("No tenants found. Please add tenants first.")
        return

    tenant = st.selectbox("Tenant", tenants, format_func=lambda x: x[1])
    ledger = tenant_ledger(tenant[0])

    if ledger:
        df = pd.DataFrame(
            [(fmt(r[0], r[2]), r[1]) for r in ledger],
            columns=["Amount", "Date"],
        )
        st.dataframe(df, width="stretch", hide_index=True)
        # Show totals per currency
        totals: dict[str, float] = {}
        for r in ledger:
            totals[r[2]] = totals.get(r[2], 0.0) + r[0]
        total_str = "  |  ".join(fmt(v, k) for k, v in totals.items())
        st.metric("Total paid", total_str)
    else:
        st.info("No payments recorded for this tenant.")
