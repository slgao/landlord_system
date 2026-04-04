import streamlit as st
from pathlib import Path
from db import fetch, get_tenant_address, get_tenant_gender
from pdfgen import generate_mahnung


def show():
    st.header("Mahnung Generator")

    tenants = fetch("SELECT id, name FROM tenants")
    if not tenants:
        st.info("No tenants found. Please add tenants first.")
        return

    tenant_choice = st.selectbox("Tenant", tenants, format_func=lambda x: x[1])
    tenant = tenant_choice[1]
    amount = st.number_input("Open amount (€)", min_value=0.0)

    address = get_tenant_address(tenant)
    if address:
        st.info(f"Address from contract: {address}")
    else:
        address = st.text_input("Tenant address (no contract found — enter manually)")

    if st.button("Generate Mahnung"):
        sig_path = "pdf/signature.png"
        file = generate_mahnung(
            tenant, amount, address,
            gender=get_tenant_gender(tenant),
            signature_path=sig_path if Path(sig_path).exists() else None
        )
        with open(file, "rb") as f:
            st.download_button("Download Mahnung", f, file_name=file)
