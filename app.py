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
import pandas as pd

from db import *
from logic import *
from pdfgen import *

init_db()

st.title("Landlord Management System")

menu = st.sidebar.selectbox(

"Menu",

[
"Dashboard",
"Properties",
"Apartments",
"Tenants",
"Contracts",
"Rent Tracking",
"Nebenkostenabrechnung",
"Mahnung Generator"
]

)

st.set_page_config(
page_title="Landlord Management System",
layout="wide"
)

if menu == "Dashboard":

    st.header("Property Dashboard")

    properties = fetch("SELECT * FROM properties")
    tenants = fetch("SELECT * FROM tenants")

    st.metric("Properties",len(properties))
    st.metric("Tenants",len(tenants))


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
            use_container_width=True,
            hide_index=True
        )


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

    data = fetch("SELECT * FROM apartments")
    df = pd.DataFrame(data, columns=["ID","Property","Apartment"])
    st.dataframe(df)


if menu == "Tenants":

    st.header("Tenants")

    name = st.text_input("Tenant name")
    email = st.text_input("Email")

    if st.button("Add Tenant"):

        insert(
            "tenants",
            (name, email)
        )

        st.success("Tenant added")

    st.divider()

    st.subheader("Tenant List")

    data = fetch("SELECT id, name, email FROM tenants")

    if len(data) == 0:
        st.info("No tenants yet")

    else:

        data = fetch("""
        SELECT
        tenants.name,
        tenants.email,
        apartments.name
        FROM tenants
        LEFT JOIN contracts
        ON tenants.id = contracts.tenant_id
        LEFT JOIN apartments
        ON contracts.apartment_id = apartments.id
        """)

        df = pd.DataFrame(
        data,
        columns=["Tenant", "Email", "Apartment"]
        )

        st.dataframe(df, use_container_width=True)


if menu == "Contracts":

    st.header("Tenant Contracts")

    tenants = fetch("SELECT id,name FROM tenants")
    apartments = fetch("SELECT id,name FROM apartments")

    if len(tenants) == 0 or len(apartments) == 0:
        st.warning("Please create tenants and apartments first")

    else:

        tenant_choice = st.selectbox(
            "Tenant",
            tenants,
            format_func=lambda x: x[1]
        )

        apartment_choice = st.selectbox(
            "Apartment",
            apartments,
            format_func=lambda x: x[1]
        )

        rent = st.number_input("Monthly Rent", value=650.0)

        move_in = st.date_input("Move in date")

        if st.button("Create Contract"):

            insert(
                "contracts",
                (
                    tenant_choice[0],
                    apartment_choice[0],
                    rent,
                    move_in,
                    None
                )
            )

            st.success("Contract created")


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
                "rent_payments",
                (
                    contract_choice[0],
                    amount,
                    pay_date
                )
            )

            st.success("Payment recorded")


if menu == "Nebenkostenabrechnung":

    st.header("Generate Abrechnung")

    tenant=st.text_input("Tenant")

    address=st.text_input("Address")

    strom_start=st.date_input("Strom Start")
    strom_end=st.date_input("Strom End")

    strom_cost=st.number_input("Electricity cost")

    days=(strom_end-strom_start).days

    tenants=st.number_input("Tenants in flat",value=3)

    strom_cost_tenant,strom_limit,strom_nach = strom_calc(strom_cost,tenants,days)

    bk_start=st.date_input("BK Start")
    bk_end=st.date_input("BK End")

    months=st.number_input("Months",value=3)

    bk_cost=st.number_input("Total Betriebskosten")

    bk_tenant,bk_period,bk_limit,bk_nach = betriebskosten_calc(bk_cost,tenants,months)

    if st.button("Generate PDF"):

        file = invoice_pdf(

        tenant,
        address,

        f"{strom_start} - {strom_end}",
        days,
        strom_cost,
        strom_limit,
        strom_nach,

        f"{bk_start} - {bk_end}",
        months,
        bk_period,
        bk_limit,
        bk_nach

        )

        with open(file,"rb") as f:

            st.download_button("Download",f,file_name=file)


if menu == "Mahnung Generator":

    tenant=st.text_input("Tenant")

    amount=st.number_input("Open amount")

    if st.button("Generate Mahnung"):

        file=mahnung_pdf(tenant,amount)

        with open(file,"rb") as f:

            st.download_button("Download Mahnung",f,file_name=file)
