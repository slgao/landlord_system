import streamlit as st
import pandas as pd
from db import fetch
from logic import tenant_ledger


def show():
    st.header("Tenant Ledger")

    tenants = fetch("SELECT id, name FROM tenants")
    if not tenants:
        st.info("No tenants found. Please add tenants first.")
        return

    tenant = st.selectbox("Tenant", tenants, format_func=lambda x: x[1])
    ledger = tenant_ledger(tenant[0])

    if ledger:
        df = pd.DataFrame(ledger, columns=["Amount (€)", "Date"])
        st.dataframe(df, width="stretch", hide_index=True)
        st.metric("Total paid", f"€ {sum(r[0] for r in ledger):,.2f}")
    else:
        st.info("No payments recorded for this tenant.")
