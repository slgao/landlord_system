#! /usr/bin/env python
# coding=utf-8
# ================================================================
#   Copyright (C) 2026 * Ltd. All rights reserved.
#
#   Editor      : EMACS
#   File name   : app.py
#   Author      : slgao
#   Created date: Sun Mar 08 2026 16:11:33
#   Description :
#
# ================================================================

import streamlit as st
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

from db import *
from logic import *
from pdfgen import *

init_db()

st.set_page_config(
    page_title="Landlord Management System",
    layout="wide"
)

menu = st.sidebar.selectbox(

"Menu",

[
"Dashboard",
"Properties",
"Apartments",
"Tenants",
"Tenant Ledger",
"Contracts",
"Rent Tracking",
"Nebenkostenabrechnung",
"Mahnung Generator"
]

)

if menu == "Dashboard":
    st.header("Property Dashboard")

    # Basic Metrics
    properties = fetch("SELECT * FROM properties")
    tenants = fetch("SELECT * FROM tenants")
    st.metric("Properties", len(properties))
    st.metric("Tenants", len(tenants))

    st.divider()
    st.subheader("⚠️ Expiring Contracts (Next 90 Days)")

    # Fetch contracts with end dates
    upcoming_expirations = fetch("""
        SELECT t.name, a.name, c.end_date 
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        WHERE c.end_date IS NOT NULL 
        AND c.end_date != 'None'
    """)

    alerts_found = False
    today = date.today()

    for t_name, a_name, end_date_str in upcoming_expirations:
        try:
            # Convert stored string back to date object for comparison
            end_date = date.fromisoformat(end_date_str)
            days_until = (end_date - today).days

            if 0 <= days_until <= 90:
                st.warning(f"**{t_name}** ({a_name}) - Ends in {days_until} days ({end_date})")
                alerts_found = True
            elif days_until < 0:
                st.error(f"**{t_name}** ({a_name}) - EXPIRED on {end_date}")
                alerts_found = True
        except ValueError:
            continue

    if not alerts_found:
        st.success("No contracts expiring in the next 90 days.")


if menu == "Properties":

    st.header("Properties")

    name = st.text_input("Property name")
    address = st.text_input("Address")

    if st.button("Add Property"):

        insert(
            "properties",
            (name, address)
        )

        st.success("Property added")

    st.divider()

    st.subheader("Property List")

    data = fetch("SELECT id, name, address FROM properties")

    if len(data) == 0:
        st.info("No properties yet")

    else:

        df = pd.DataFrame(
            data,
            columns=["ID", "Property Name", "Address"]
        )

        st.dataframe(
            df,
            width='stretch',
            hide_index=True
        )
        
        # Delete Section
        st.divider()
        st.subheader("Delete Property")
        delete_id = st.number_input("Enter Property ID to delete", step=1, min_value=1)
        if st.button("Delete Property", type="primary"):
            delete("properties", delete_id)
            st.success(f"Property {delete_id} deleted!")
            st.rerun() # Refresh the app to show updated list


if menu == "Apartments":

    st.header("Apartments")

    properties = fetch("SELECT id,name FROM properties")

    if len(properties) == 0:
        st.warning("Please create a property first")
    else:

        property_choice = st.selectbox(
            "Property",
            properties,
            format_func=lambda x: x[1]
        )

        apartment_name = st.text_input("Apartment name (e.g. Wohnung 1 / WG Zimmer A)")

        if st.button("Add Apartment"):

            insert(
                "apartments",
                (property_choice[0], apartment_name)
            )

            st.success("Apartment added")

    st.subheader("Existing Apartments")

    apt_data = fetch("SELECT id, property_id, name FROM apartments")
    if apt_data:
        df_apt = pd.DataFrame(apt_data, columns=["ID", "Property ID", "Apartment Name"])
        st.dataframe(df_apt, width='stretch', hide_index=True)

        # Deletion logic
        apt_ids = [row[0] for row in apt_data]
        apt_id_to_delete = st.selectbox("Select Apartment ID to delete", apt_ids)
        
        if st.button("Delete Apartment", type="primary"):
            execute("DELETE FROM apartments WHERE id = ?", (apt_id_to_delete,))
            st.success(f"Apartment {apt_id_to_delete} removed")
            st.rerun()
    else:
        st.info("No apartments found.")

if menu == "Tenants":
    st.header("Tenants")
    
    # Adding a tenant
    name = st.text_input("Tenant name")
    email = st.text_input("Email")
    gender = st.selectbox("Gender", ["male", "female", "diverse"])
    if st.button("Add Tenant"):
        insert("tenants", (name, email, gender))
        st.success("Tenant added")
        st.rerun()

    st.divider()
    st.subheader("Tenant List")
    
    data = fetch("""
        SELECT tenants.id, tenants.name, tenants.email, tenants.gender, apartments.name
        FROM tenants
        LEFT JOIN contracts ON tenants.id = contracts.tenant_id
        LEFT JOIN apartments ON contracts.apartment_id = apartments.id
    """)

    if not data:
        st.info("No tenants yet")
    else:
        df = pd.DataFrame(data, columns=["ID", "Tenant", "Email", "Gender", "Apartment"])
        st.dataframe(df, width='stretch', hide_index=True)

        st.subheader("Remove a Tenant")
        tenant_ids = [row[0] for row in data]
        id_to_delete = st.selectbox("Select ID to delete", tenant_ids)
        
        if st.button("Delete Tenant", type="primary"):
            execute("DELETE FROM tenants WHERE id = ?", (id_to_delete,))
            st.success(f"Tenant {id_to_delete} removed")
            st.rerun()

        st.divider()
        st.subheader("Update Gender")
        tenant_options = [(row[0], row[1]) for row in data]
        tenant_to_edit = st.selectbox("Select Tenant", tenant_options, format_func=lambda x: x[1], key="gender_edit")
        new_gender = st.selectbox("Gender", ["male", "female", "diverse"], key="gender_val")
        if st.button("Save Gender"):
            execute("UPDATE tenants SET gender = ? WHERE id = ?", (new_gender, tenant_to_edit[0]))
            st.success(f"Gender updated for {tenant_to_edit[1]}")
            st.rerun()


if menu == "Tenant Ledger":

    tenants = fetch("SELECT id,name FROM tenants")

    if not tenants:
        st.info("No tenants found. Please add tenants first.")
    else:
        tenant = st.selectbox(
            "Tenant",
            tenants,
            format_func=lambda x: x[1]
        )

        ledger = tenant_ledger(tenant[0])

        df = pd.DataFrame(
            ledger,
            columns=["Amount","Date"]
        )

        st.dataframe(df,width='stretch')


if menu == "Contracts":
    st.header("Tenant Contracts")

    tenants = fetch("SELECT id, name FROM tenants")
    apartments = fetch("SELECT id, name FROM apartments")

    if len(tenants) == 0 or len(apartments) == 0:
        st.warning("Please create tenants and apartments first")
    else:
        tenant_choice = st.selectbox("Tenant", tenants, format_func=lambda x: x[1])
        apartment_choice = st.selectbox("Apartment", apartments, format_func=lambda x: x[1])
        rent = st.number_input("Monthly Rent", value=650.0)

        col1, col2 = st.columns(2)
        with col1:
            move_in = st.date_input("Move in date", min_value=date.today() - timedelta(days=365*20))
        
        # Logic for limited contracts
        is_limited = st.checkbox("Limited Contract (Fixed Term)")
        move_out = None
        
        if is_limited:
            with col2:
                move_out = st.date_input("Move out date")

        if st.button("Create Contract"):
            insert(
                "contracts",
                (
                    tenant_choice[0],
                    apartment_choice[0],
                    rent,
                    str(move_in),
                    str(move_out) if move_out else None
                )
            )
            st.success("Contract created")
            st.rerun()

    # Display existing contracts with the end date
    st.divider()
    st.subheader("Existing Contracts")
    contract_data = fetch("""
        SELECT c.id, t.name, a.name, c.rent, c.start_date, c.end_date 
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
    """)
    if contract_data:
        df_contracts = pd.DataFrame(
            contract_data, 
            columns=["ID", "Tenant", "Apartment", "Rent", "Start Date", "End Date"]
        )
        st.dataframe(df_contracts, width='stretch', hide_index=True)

        # Deletion logic
        st.divider()
        st.subheader("Terminate / Delete Contract")
        contract_ids = [row[0] for row in contract_data]
        contract_to_delete = st.selectbox("Select Contract ID to remove", contract_ids)
        
        if st.button("Delete Contract", type="primary"):
            execute("DELETE FROM contracts WHERE id = ?", (contract_to_delete,))
            st.success(f"Contract {contract_to_delete} deleted.")
            st.rerun()

if menu == "Rent Tracking":

    st.header("Rent Payments")

    contracts = fetch("""
    SELECT contracts.id, tenants.name, apartments.name
    FROM contracts
    JOIN tenants ON contracts.tenant_id = tenants.id
    JOIN apartments ON contracts.apartment_id = apartments.id
    """)

    if len(contracts) == 0:
        st.warning("No contracts found")

    else:

        contract_choice = st.selectbox(
            "Contract",
            contracts,
            format_func=lambda x: f"{x[1]} - {x[2]}"
        )

        amount = st.number_input("Payment amount", value=650.0)

        pay_date = st.date_input("Payment date")

        if st.button("Add Payment"):

            insert(
                "payments",
                (
                    contract_choice[0],
                    amount,
                    pay_date
                )
            )

            st.success("Payment recorded")

        st.divider()
        st.subheader("Payment History")

        payments = fetch("""
            SELECT payments.id, tenants.name, apartments.name, payments.amount, payments.payment_date
            FROM payments
            JOIN contracts ON payments.contract_id = contracts.id
            JOIN tenants ON contracts.tenant_id = tenants.id
            JOIN apartments ON contracts.apartment_id = apartments.id
            WHERE payments.contract_id = ?
        """, (contract_choice[0],))

        if payments:
            df_payments = pd.DataFrame(payments, columns=["ID", "Tenant", "Apartment", "Amount", "Date"])
            st.dataframe(df_payments, width='stretch', hide_index=True)

            payment_id_to_delete = st.selectbox("Select Payment ID to delete", [p[0] for p in payments])
            if st.button("Delete Payment", type="primary"):
                execute("DELETE FROM payments WHERE id = ?", (payment_id_to_delete,))
                st.success(f"Payment {payment_id_to_delete} deleted.")
                st.rerun()
        else:
            st.info("No payments recorded for this contract.")

    # Monthly overview across all properties and tenants
    st.divider()
    st.subheader("Monthly Overview")

    today = date.today()
    selected_month = st.date_input(
        "Select month",
        value=today.replace(day=1),
        format="YYYY-MM-DD"
    )

    month_start = selected_month.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    monthly_payments = fetch("""
        SELECT p.name AS property, a.name AS apartment, t.name AS tenant,
               pay.amount, pay.payment_date
        FROM payments pay
        JOIN contracts c ON pay.contract_id = c.id
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE pay.payment_date >= ? AND pay.payment_date < ?
        ORDER BY p.name, a.name, pay.payment_date
    """, (str(month_start), str(month_end)))

    if monthly_payments:
        df_monthly = pd.DataFrame(
            monthly_payments,
            columns=["Property", "Apartment", "Tenant", "Amount", "Date"]
        )
        st.dataframe(df_monthly, width='stretch', hide_index=True)
        st.metric("Total collected", f"€ {sum(r[3] for r in monthly_payments):,.2f}")
    else:
        st.info(f"No payments recorded for {month_start.strftime('%B %Y')}.")


if menu == "Nebenkostenabrechnung":

    st.header("Generate Abrechnung")

    landlord_name = st.text_input("Landlord name", value="Ihr Vermieter")

    sig_path = "pdf/signature.png"
    if Path(sig_path).exists():
        st.image(sig_path, width=200, caption="Current signature")
    sig_upload = st.file_uploader("Upload signature image (PNG/JPG)", type=["png", "jpg", "jpeg"], key="sig_abrechnung")
    if sig_upload:
        Path("pdf").mkdir(exist_ok=True)
        with open(sig_path, "wb") as f:
            f.write(sig_upload.read())
        st.success("Signature saved.")

    contract_tenants = fetch("""
        SELECT DISTINCT t.id, t.name FROM tenants t
        JOIN contracts c ON c.tenant_id = t.id
    """)

    if not contract_tenants:
        st.warning("No tenants with contracts found.")
        st.stop()

    tenant_choice = st.selectbox("Tenant", contract_tenants, format_func=lambda x: x[1])
    tenant = tenant_choice[1]
    address = get_tenant_address(tenant) or ""
    gender = get_tenant_gender(tenant)
    st.info(f"Address: {address}" if address else "No address found for this tenant.")

    st.divider()

    tenants = st.number_input("Tenants in flat", value=3)

    st.subheader("Strom")
    strom_start = st.date_input("Strom Start")
    strom_end = st.date_input("Strom End")
    strom_limit_per_month = st.number_input("Electricity prepayment per month (€)")
    strom_cost = st.number_input("Total electricity cost flat (€)")
    days = (strom_end - strom_start).days

    strom_cost_tenant, strom_limit, strom_nach = strom_calc(strom_cost, tenants, days, limit_per_month=strom_limit_per_month)

    st.subheader("Betriebskosten")
    bk_start = st.date_input("BK Start")
    bk_end = st.date_input("BK End")
    bk_limit_per_month = st.number_input("Betriebskosten prepayment per month (€)")
    months = st.number_input("Months", value=3)
    bk_cost = st.number_input("Total Betriebskosten (€)")

    bk_tenant, bk_period, bk_limit, bk_nach = betriebskosten_calc(bk_cost, tenants, months, bk_start, bk_end, limit_per_month=bk_limit_per_month)

    if st.button("Generate PDF"):
        file = invoice_pdf(
            tenant, address,
            f"{strom_start} - {strom_end}", days, strom_cost, strom_limit, strom_nach,
            f"{bk_start} - {bk_end}", months, bk_period, bk_limit, bk_nach,
            landlord_name=landlord_name,
            num_tenants=int(tenants),
            monthly_strom_limit=strom_limit_per_month,
            monthly_bk_limit=bk_limit_per_month,
            gender=gender,
            signature_path=sig_path if Path(sig_path).exists() else None,
        )
        with open(file, "rb") as f:
            st.download_button("Download", f, file_name=file)


if menu == "Mahnung Generator":

    tenants = fetch("SELECT id, name FROM tenants")

    if not tenants:
        st.info("No tenants found. Please add tenants first.")
    else:
        tenant_choice = st.selectbox("Tenant", tenants, format_func=lambda x: x[1])
        tenant = tenant_choice[1]
        amount = st.number_input("Open amount")

        address = get_tenant_address(tenant)

        if address:
            st.info(f"Address from contract: {address}")
        else:
            address = st.text_input("Tenant Address (no contract found — enter manually)")

        if st.button("Generate Mahnung"):
            sig_path = "pdf/signature.png"
            file = generate_mahnung(tenant, amount, address,
                                    gender=get_tenant_gender(tenant),
                                    signature_path=sig_path if Path(sig_path).exists() else None)

            with open(file, "rb") as f:
                st.download_button("Download Mahnung", f, file_name=file)
