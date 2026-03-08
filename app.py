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
from datetime import date
from database import init_db, add_tenant, get_tenants
from invoice import create_invoice

init_db()

st.title("Landlord Management Tool")

menu = st.sidebar.selectbox(
    "Menu",
    ["Add Tenant","Generate Abrechnung"]
)

if menu == "Add Tenant":

    st.header("Add Tenant")

    name = st.text_input("Tenant Name")
    address = st.text_input("Address")
    tenants = st.number_input("Tenants in flat",value=3)

    if st.button("Save"):

        add_tenant(name,address,tenants)

        st.success("Tenant saved")


if menu == "Generate Abrechnung":

    tenants = get_tenants()

    tenant_names = {f"{t[1]} ({t[2]})":t for t in tenants}

    selected = st.selectbox("Select Tenant",list(tenant_names.keys()))

    tenant = tenant_names[selected]

    tenant_name = tenant[1]
    address = tenant[2]
    tenant_count = tenant[3]

    st.subheader("Electricity")

    strom_start = st.date_input("Start")
    strom_end = st.date_input("End")

    strom_cost = st.number_input("Total electricity cost (€)",value=1000.0)

    strom_days = (strom_end - strom_start).days

    st.subheader("Betriebskosten")

    betriebskosten_start = st.date_input("Start BK")
    betriebskosten_end = st.date_input("End BK")

    betriebskosten_flat = st.number_input("Total Betriebskosten (€)",value=3000.0)

    betriebskosten_months = st.number_input("Months tenant lived",value=3)

    if st.button("Generate PDF"):

        pdf = create_invoice(

            tenant_name,
            address,

            strom_start,
            strom_end,
            strom_days,
            strom_cost,

            betriebskosten_start,
            betriebskosten_end,
            betriebskosten_months,
            betriebskosten_flat,

            tenant_count

        )

        with open(pdf,"rb") as f:

            st.download_button(

                "Download Abrechnung",
                f,
                file_name=f"Abrechnung_{tenant_name}.pdf"
            )
