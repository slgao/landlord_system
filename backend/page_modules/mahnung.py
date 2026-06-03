import streamlit as st
from pathlib import Path
from db import fetch, get_tenant_gender
from pdfgen import generate_mahnung


def show():
    st.header("Mahnung Generator")

    contract_tenants = fetch("""
        SELECT DISTINCT t.id, t.name FROM tenants t
        JOIN contracts c ON c.tenant_id = t.id
    """)
    if not contract_tenants:
        st.info("No tenants with contracts found.")
        return

    tenant_choice = st.selectbox("Tenant", contract_tenants, format_func=lambda x: x[1])
    tenant = tenant_choice[1]
    gender = get_tenant_gender(tenant)

    # ── Contract selector (for multi-contract tenants) ─────────────
    all_contracts = fetch("""
        SELECT c.id, c.start_date, c.end_date, a.name, a.id
        FROM contracts c
        JOIN apartments a ON c.apartment_id = a.id
        WHERE c.tenant_id=? ORDER BY c.start_date DESC
    """, (tenant_choice[0],))

    def _fmt(row):
        _, s, e, apt, _ = row
        return f"{apt}  ({s} – {e if e and e != 'None' else 'unbefristet'})"

    if len(all_contracts) > 1:
        contract_row = st.selectbox("Contract / Apartment", all_contracts,
                                    format_func=_fmt, key="mahnung_contract_sel")
    else:
        contract_row = all_contracts[0]

    selected_contract_id  = contract_row[0]
    selected_apartment_id = contract_row[4]

    # Address from selected contract's property
    addr_row = fetch("""
        SELECT p.address FROM apartments a
        JOIN properties p ON p.id = a.property_id WHERE a.id = ?
    """, (selected_apartment_id,))
    address = addr_row[0][0] if addr_row and addr_row[0][0] else ""

    # Co-tenants in contract only
    co_tenants_rows = fetch(
        "SELECT name, gender FROM co_tenants "
        "WHERE contract_id=? AND in_contract=1 ORDER BY id",
        (selected_contract_id,)
    )
    co_tenants = [{"name": r[0], "gender": r[1]} for r in co_tenants_rows]

    info = f"**Apartment:** {contract_row[3]}"
    if co_tenants:
        info += "  \n**Co-tenants (in contract):** " + ", ".join(c["name"] for c in co_tenants)
    if address:
        info += f"  \n**Address:** {address}"
    else:
        address = st.text_input("Tenant address (none found — enter manually)")
    st.info(info)

    amount = st.number_input("Open amount (€)", min_value=0.0)

    if st.button("Generate Mahnung"):
        sig_path = "pdf/signature.png"
        file = generate_mahnung(
            tenant, amount, address,
            gender=gender,
            signature_path=sig_path if Path(sig_path).exists() else None,
            co_tenants=co_tenants if co_tenants else None,
        )
        with open(file, "rb") as f:
            st.download_button("Download Mahnung", f, file_name=file)
