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
import calendar
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
"Flat Costs",
"Balance Sheet",
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


elif menu == "Properties":

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


elif menu == "Apartments":

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

        apartment_name = st.text_input(
            "Room / Apartment name",
            placeholder="e.g. Wohnung 1 - Zimmer A",
            help="**WG (shared flat):** Enter each room separately, e.g. 'Wohnung 1 - Zimmer A', 'Wohnung 1 - Zimmer B'.\n\n"
                 "**Whole apartment:** Enter the apartment name, e.g. 'Wohnung 2'. "
                 "This is the name shown in contracts and rent tracking."
        )
        flat_name = st.text_input(
            "Flat / Wohnung",
            placeholder="e.g. Wohnung 1",
            help="**WG:** All rooms in the same flat share the same label here, e.g. 'Wohnung 1'. "
                 "This is used to auto-count how many people share the flat for Nebenkostenabrechnung.\n\n"
                 "**Whole apartment:** Same as the room name above, e.g. 'Wohnung 2'.\n\n"
                 "Leave empty if not needed."
        )

        if st.button("Add Apartment"):
            insert("apartments", (property_choice[0], apartment_name, flat_name))
            st.success("Apartment added")

    st.subheader("Existing Apartments")

    apt_data = fetch("SELECT id, property_id, name, flat FROM apartments")
    if apt_data:
        df_apt = pd.DataFrame(apt_data, columns=["ID", "Property ID", "Room/Apartment", "Flat"])
        st.dataframe(df_apt, width='stretch', hide_index=True)

        # Deletion logic
        apt_ids = [row[0] for row in apt_data]
        apt_id_to_delete = st.selectbox("Select Apartment ID to delete", apt_ids)
        
        if st.button("Delete Apartment", type="primary"):
            execute("DELETE FROM apartments WHERE id = ?", (apt_id_to_delete,))
            st.success(f"Apartment {apt_id_to_delete} removed")
            st.rerun()

        st.divider()
        st.subheader("Edit Apartment")
        apt_to_edit = st.selectbox("Select Apartment", apt_data,
                                   format_func=lambda x: f"#{x[0]} — {x[2]} ({x[3] or 'no flat'})",
                                   key="apt_edit")
        col1, col2 = st.columns(2)
        with col1:
            new_apt_name = st.text_input("Room / Apartment name", value=apt_to_edit[2],
                                         placeholder="e.g. Zimmer A, Wohnung 2",
                                         help="The individual room or unit name.",
                                         key=f"apt_name_{apt_to_edit[0]}")
        with col2:
            new_flat = st.text_input("Flat / Wohnung", value=apt_to_edit[3] or "",
                                     placeholder="e.g. Wohnung 1, EG Links",
                                     help="Rooms sharing the same flat get the same label here. "
                                          "Used to auto-count persons for Nebenkostenabrechnung.",
                                     key=f"apt_flat_{apt_to_edit[0]}")
        if st.button("Save Apartment"):
            execute("UPDATE apartments SET name = ?, flat = ? WHERE id = ?",
                    (new_apt_name, new_flat, apt_to_edit[0]))
            st.success("Apartment updated.")
            st.rerun()
    else:
        st.info("No apartments found.")

elif menu == "Tenants":
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
        st.subheader("Edit Tenant")
        tenant_options = [(row[0], row[1], row[2], row[3]) for row in data]  # id, name, email, gender
        tenant_to_edit = st.selectbox("Select Tenant", tenant_options, format_func=lambda x: x[1], key="tenant_edit")

        col1, col2 = st.columns(2)
        with col1:
            new_name  = st.text_input("Name",   value=tenant_to_edit[1], key=f"edit_name_{tenant_to_edit[0]}")
            new_email = st.text_input("Email",  value=tenant_to_edit[2] or "", key=f"edit_email_{tenant_to_edit[0]}")
        with col2:
            gender_options = ["male", "female", "diverse"]
            current_gender = tenant_to_edit[3] if tenant_to_edit[3] in gender_options else "diverse"
            new_gender = st.selectbox("Gender", gender_options,
                                      index=gender_options.index(current_gender), key=f"edit_gender_{tenant_to_edit[0]}")

        # Apartment reassignment
        all_apartments = fetch("SELECT id, name FROM apartments")
        current_apt = fetch("""
            SELECT apartment_id FROM contracts WHERE tenant_id = ? LIMIT 1
        """, (tenant_to_edit[0],))
        current_apt_id = current_apt[0][0] if current_apt else None
        apt_ids = [a[0] for a in all_apartments]
        apt_index = apt_ids.index(current_apt_id) if current_apt_id in apt_ids else 0

        if all_apartments:
            new_apt = st.selectbox("Apartment (via contract)", all_apartments,
                                   format_func=lambda x: x[1],
                                   index=apt_index, key=f"edit_apt_{tenant_to_edit[0]}")
        else:
            new_apt = None

        if st.button("Save Changes"):
            execute("UPDATE tenants SET name = ?, email = ?, gender = ? WHERE id = ?",
                    (new_name, new_email, new_gender, tenant_to_edit[0]))
            if new_apt and current_apt_id:
                execute("UPDATE contracts SET apartment_id = ? WHERE tenant_id = ?",
                        (new_apt[0], tenant_to_edit[0]))
            st.success(f"Tenant {new_name} updated.")
            st.rerun()


elif menu == "Tenant Ledger":

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


elif menu == "Contracts":
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
            # Check for overlapping active contract on same apartment
            overlap = fetch("""
                SELECT t.name FROM contracts c
                JOIN tenants t ON c.tenant_id = t.id
                WHERE c.apartment_id = ?
                AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= ?)
                AND c.start_date <= ?
            """, (apartment_choice[0], str(move_in), str(move_out) if move_out else "9999-12-31"))
            if overlap:
                st.warning(f"⚠️ Apartment already occupied by **{overlap[0][0]}** in this period. "
                           "Terminate their contract first or adjust the dates.")
            else:
                insert(
                    "contracts",
                    (
                        tenant_choice[0],
                        apartment_choice[0],
                        rent,
                        str(move_in),
                        str(move_out) if move_out else None,
                        None,
                        None,
                        None,
                        None
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

        def highlight_contracts(row):
            end = row["End Date"]
            if not end or end == "None":
                return [""] * len(row)
            try:
                d = date.fromisoformat(end)
                if d < date.today():
                    return ["background-color: #c0392b; color: white"] * len(row)  # expired
                elif (d - date.today()).days <= 90:
                    return ["background-color: #e67e22; color: white"] * len(row)  # expiring soon
            except ValueError:
                pass
            return [""] * len(row)

        st.dataframe(df_contracts.style.apply(highlight_contracts, axis=1),
                     width='stretch', hide_index=True)
        st.caption("🔴 Expired &nbsp;&nbsp; 🟡 Expiring within 90 days")

        # Deletion logic
        st.divider()
        st.subheader("Edit Contract")
        contract_choice = st.selectbox(
            "Select Contract to edit",
            contract_data,
            format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
            key="contract_edit"
        )
        cid, _, _, c_rent, c_start, c_end = contract_choice

        apartments_all = fetch("SELECT id, name FROM apartments")
        apt_ids = [a[0] for a in apartments_all]
        # find current apartment id
        c_apt_id = fetch("SELECT apartment_id FROM contracts WHERE id = ?", (cid,))[0][0]
        apt_index = apt_ids.index(c_apt_id) if c_apt_id in apt_ids else 0

        col1, col2 = st.columns(2)
        with col1:
            edit_apt = st.selectbox("Apartment", apartments_all, format_func=lambda x: x[1],
                                    index=apt_index, key=f"cedit_apt_{cid}")
            edit_rent = st.number_input("Monthly Rent (€)", value=float(c_rent), key=f"cedit_rent_{cid}")
        with col2:
            edit_start = st.date_input("Start date", value=date.fromisoformat(c_start),
                                       min_value=date.today() - timedelta(days=365*20),
                                       key=f"cedit_start_{cid}")
            edit_limited = st.checkbox("Fixed Term", value=bool(c_end and c_end != "None"),
                                       key=f"cedit_limited_{cid}")
            edit_end = None
            if edit_limited:
                edit_end = st.date_input("End date",
                                         value=date.fromisoformat(c_end) if c_end and c_end != "None" else date.today(),
                                         key=f"cedit_end_{cid}")

        if st.button("Save Contract Changes"):
            execute("""
                UPDATE contracts SET apartment_id=?, rent=?, start_date=?, end_date=? WHERE id=?
            """, (edit_apt[0], edit_rent, str(edit_start), str(edit_end) if edit_end else None, cid))
            st.success("Contract updated.")
            st.rerun()

        st.divider()
        st.subheader("Terminate Contract (Move-out)")
        # Only show active (open-ended or future end date) contracts
        active_contracts = [r for r in contract_data if not r[5] or r[5] == 'None' or r[5] >= str(date.today())]
        if active_contracts:
            contract_to_terminate = st.selectbox(
                "Select active contract to terminate",
                active_contracts,
                format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                key="terminate_select"
            )
            move_out_date = st.date_input("Move-out date", value=date.today(), key="move_out_date")
            if st.button("Terminate Contract"):
                execute("UPDATE contracts SET end_date = ? WHERE id = ?",
                        (str(move_out_date), contract_to_terminate[0]))
                st.success(f"{contract_to_terminate[1]} terminated on {move_out_date}.")
                st.rerun()
        else:
            st.info("No active contracts to terminate.")

        st.divider()
        st.subheader("Delete Contract")
        contract_ids = [row[0] for row in contract_data]
        contract_to_delete = st.selectbox("Select Contract ID to remove", contract_ids)
        
        if st.button("Delete Contract", type="primary"):
            execute("DELETE FROM contracts WHERE id = ?", (contract_to_delete,))
            st.success(f"Contract {contract_to_delete} deleted.")
            st.rerun()

        # ── Kaution ────────────────────────────────────────────────
        st.divider()
        st.subheader("Kaution (Deposit)")

        kaution_data = fetch("""
            SELECT c.id, t.name, a.name,
                   c.kaution_amount, c.kaution_paid_date,
                   c.kaution_returned_date, c.kaution_returned_amount
            FROM contracts c
            JOIN tenants t ON c.tenant_id = t.id
            JOIN apartments a ON c.apartment_id = a.id
        """)

        df_kaution = pd.DataFrame(kaution_data,
            columns=["Contract ID", "Tenant", "Apartment",
                     "Kaution (€)", "Paid Date", "Returned Date", "Returned (€)"])
        st.dataframe(df_kaution, width='stretch', hide_index=True)

        st.markdown("**Record / Update Kaution**")
        k_contract = st.selectbox("Contract", contract_data,
                                  format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                                  key="kaution_contract")
        col1, col2 = st.columns(2)
        with col1:
            k_amount = st.number_input("Kaution amount (€)", min_value=0.0, key="k_amount")
            k_paid = st.date_input("Date received", key="k_paid")
        with col2:
            k_returned = st.date_input("Date returned (leave if not yet)", key="k_returned")
            k_returned_amt = st.number_input("Amount returned (€)", min_value=0.0, key="k_returned_amt")

        if st.button("Save Kaution"):
            execute("""
                UPDATE contracts SET
                    kaution_amount = ?,
                    kaution_paid_date = ?,
                    kaution_returned_date = ?,
                    kaution_returned_amount = ?
                WHERE id = ?
            """, (k_amount, str(k_paid),
                  str(k_returned) if k_returned_amt > 0 else None,
                  k_returned_amt if k_returned_amt > 0 else None,
                  k_contract[0]))
            st.success("Kaution saved.")
            st.rerun()

elif menu == "Rent Tracking":

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

            st.divider()
            st.subheader("Edit Payment")
            pay_to_edit = st.selectbox("Select Payment", payments,
                                       format_func=lambda x: f"#{x[0]} — {x[3]:.2f} € on {x[4]}",
                                       key="pay_edit")
            col1, col2 = st.columns(2)
            with col1:
                new_amount = st.number_input("Amount (€)", value=float(pay_to_edit[3]),
                                             key=f"pay_amt_{pay_to_edit[0]}")
            with col2:
                new_pay_date = st.date_input("Payment date",
                                             value=date.fromisoformat(pay_to_edit[4]),
                                             key=f"pay_date_{pay_to_edit[0]}")
            if st.button("Save Payment"):
                execute("UPDATE payments SET amount = ?, payment_date = ? WHERE id = ?",
                        (new_amount, str(new_pay_date), pay_to_edit[0]))
                st.success("Payment updated.")
                st.rerun()

            st.divider()
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


elif menu == "Flat Costs":
    st.header("Flat Costs")

    apartments = fetch("SELECT id, name, flat FROM apartments")
    if not apartments:
        st.warning("No apartments found.")
    else:
        st.subheader("Add Cost")
        apt_choice = st.selectbox("Apartment", apartments,
                                  format_func=lambda x: f"{x[1]} ({x[2]})" if x[2] else x[1])
        col1, col2 = st.columns(2)
        with col1:
            cost_type_sel = st.selectbox("Cost type", ["Hausgeld", "Mortgage", "Grundsteuer",
                                                        "Strom Vorauszahlung", "Internet", "Other"])
            cost_type = st.text_input("Custom type", key="add_custom_type") if cost_type_sel == "Other" else cost_type_sel
            amount = st.number_input("Amount (€)", min_value=0.0)
        with col2:
            frequency = st.selectbox("Frequency", ["monthly", "annual", "one-time"])
            valid_from = st.date_input("Valid from")
            valid_to_enabled = st.checkbox("Set end date")
            valid_to = st.date_input("Valid to") if valid_to_enabled else None

        if st.button("Add Cost"):
            insert("flat_costs", (apt_choice[0], cost_type, amount, frequency,
                                  str(valid_from), str(valid_to) if valid_to else None))
            st.success("Cost added.")
            st.rerun()

        st.divider()
        st.subheader("Existing Costs")
        costs = fetch("""
            SELECT fc.id, p.name, a.name, a.flat, fc.cost_type, fc.amount, fc.frequency, fc.valid_from, fc.valid_to
            FROM flat_costs fc
            JOIN apartments a ON fc.apartment_id = a.id
            JOIN properties p ON a.property_id = p.id
            ORDER BY p.name, a.flat, fc.cost_type
        """)
        if costs:
            # Group by property + flat
            from itertools import groupby
            for (prop, flat), group in groupby(costs, key=lambda x: (x[1], x[3])):
                label = f"{prop} — {flat}" if flat else f"{prop} — (no flat)"
                st.markdown(f"**{label}**")
                group_rows = list(group)
                df_group = pd.DataFrame(
                    [(r[0], r[4], r[5], r[6], r[7], r[8]) for r in group_rows],
                    columns=["ID", "Type", "Amount (€)", "Frequency", "Valid From", "Valid To"]
                )
                st.dataframe(df_group, width='stretch', hide_index=True)
                st.write("")

            # costs rows: (id, prop, apt, flat, type, amt, freq, from, to)
            all_costs = fetch("""
                SELECT fc.id, a.name, a.flat, fc.cost_type, fc.amount, fc.frequency, fc.valid_from, fc.valid_to
                FROM flat_costs fc JOIN apartments a ON fc.apartment_id = a.id
                ORDER BY a.name, fc.cost_type
            """)
            st.divider()
            st.subheader("Edit Cost")
            cost_to_edit = st.selectbox("Select Cost", all_costs,
                                        format_func=lambda x: f"#{x[0]} — {x[1]} ({x[2]}) / {x[3]} ({x[5]})",
                                        key="cost_edit")
            _, _, _, c_type, c_amt, c_freq, c_from, c_to = cost_to_edit
            type_opts = ["Hausgeld", "Mortgage", "Grundsteuer", "Strom Vorauszahlung", "Internet", "Other"]
            freq_opts = ["monthly", "annual", "one-time"]
            col1, col2 = st.columns(2)
            with col1:
                edit_type_sel = st.selectbox("Cost type", type_opts,
                                             index=type_opts.index(c_type) if c_type in type_opts else 5,
                                             key=f"cedit_type_{cost_to_edit[0]}")
                edit_type = st.text_input("Custom type", value=c_type if c_type not in type_opts else "",
                                          key=f"cedit_custom_{cost_to_edit[0]}") if edit_type_sel == "Other" else edit_type_sel
                edit_amount = st.number_input("Amount (€)", value=float(c_amt), min_value=0.0,
                                              key=f"cedit_amt_{cost_to_edit[0]}")
            with col2:
                edit_freq = st.selectbox("Frequency", freq_opts,
                                         index=freq_opts.index(c_freq) if c_freq in freq_opts else 0,
                                         key=f"cedit_freq_{cost_to_edit[0]}")
                edit_from = st.date_input("Valid from", value=date.fromisoformat(c_from),
                                          key=f"cedit_from_{cost_to_edit[0]}")
                edit_to_enabled = st.checkbox("Set end date",
                                              value=bool(c_to and c_to != "None"),
                                              key=f"cedit_to_en_{cost_to_edit[0]}")
                edit_to = st.date_input("Valid to",
                                        value=date.fromisoformat(c_to) if c_to and c_to != "None" else date.today(),
                                        key=f"cedit_to_{cost_to_edit[0]}") if edit_to_enabled else None

            if st.button("Save Cost"):
                execute("""UPDATE flat_costs SET cost_type=?, amount=?, frequency=?, valid_from=?, valid_to=?
                           WHERE id=?""",
                        (edit_type, edit_amount, edit_freq, str(edit_from),
                         str(edit_to) if edit_to else None, cost_to_edit[0]))
                st.success("Cost updated.")
                st.rerun()

            st.divider()
            del_id = st.selectbox("Select Cost ID to delete", [c[0] for c in all_costs])
            if st.button("Delete Cost", type="primary"):
                execute("DELETE FROM flat_costs WHERE id = ?", (del_id,))
                st.success("Cost deleted.")
                st.rerun()
        else:
            st.info("No costs recorded yet.")


elif menu == "Balance Sheet":
    st.header("Balance Sheet")

    year = st.selectbox("Year", list(range(date.today().year, date.today().year - 6, -1)))
    y = int(year)

    properties = fetch("SELECT id, name FROM properties")
    if not properties:
        st.warning("No properties found.")
    else:
        for prop_id, prop_name in properties:
            st.subheader(f"🏠 {prop_name}")

            max_month = date.today().month if y == date.today().year else 12
            months_labels = [date(y, m, 1).strftime("%b %Y") for m in range(1, max_month + 1)]
            rows = []
            total_income = total_costs = 0.0

            for m in range(1, max_month + 1):
                m_start = f"{y}-{m:02d}-01"
                m_end = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"

                income = fetch("""
                    SELECT COALESCE(SUM(p.amount), 0)
                    FROM payments p
                    JOIN contracts c ON p.contract_id = c.id
                    JOIN apartments a ON c.apartment_id = a.id
                    WHERE a.property_id = ? AND p.payment_date BETWEEN ? AND ?
                """, (prop_id, m_start, m_end))[0][0]

                cost_rows = fetch("""
                    SELECT fc.amount, fc.frequency, fc.valid_from, fc.valid_to
                    FROM flat_costs fc
                    JOIN apartments a ON fc.apartment_id = a.id
                    WHERE a.property_id = ?
                    AND fc.valid_from <= ? AND (fc.valid_to IS NULL OR fc.valid_to = 'None' OR fc.valid_to >= ?)
                """, (prop_id, m_end, m_start))

                costs = 0.0
                for amt, freq, vf, vt in cost_rows:
                    if freq == "monthly":
                        costs += amt
                    elif freq == "annual":
                        costs += amt / 12
                    else:  # one-time: count in the month it starts
                        if vf and vf[:7] == f"{y}-{m:02d}":
                            costs += amt

                net = income - costs
                total_income += income
                total_costs += costs
                rows.append({
                    "Month": months_labels[m-1],
                    "Income (€)": round(income, 2),
                    "Costs (€)": round(costs, 2),
                    "Net (€)": round(net, 2),
                })

            df_monthly = pd.DataFrame(rows)

            def color_net(val):
                return "color: green" if val >= 0 else "color: red"

            st.dataframe(df_monthly.style.map(color_net, subset=["Net (€)"]),
                         width='stretch', hide_index=True)

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Income", f"€ {total_income:,.2f}")
            col2.metric("Total Costs", f"€ {total_costs:,.2f}")
            col3.metric("Annual Net", f"€ {total_income - total_costs:,.2f}")
            st.divider()


elif menu == "Nebenkostenabrechnung":

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

    # Auto-count persons sharing the same flat (scoped to same property)
    persons_in_flat = fetch("""
        SELECT COUNT(DISTINCT c.tenant_id)
        FROM contracts c
        JOIN apartments a ON c.apartment_id = a.id
        WHERE (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= date('now'))
        AND a.flat IS NOT NULL AND a.flat != ''
        AND a.property_id = (
            SELECT a2.property_id FROM contracts c2
            JOIN apartments a2 ON c2.apartment_id = a2.id
            JOIN tenants t ON c2.tenant_id = t.id
            WHERE t.name = ? LIMIT 1
        )
        AND a.flat = (
            SELECT a2.flat FROM contracts c2
            JOIN apartments a2 ON c2.apartment_id = a2.id
            JOIN tenants t ON c2.tenant_id = t.id
            WHERE t.name = ? AND (a2.flat IS NOT NULL AND a2.flat != '')
            LIMIT 1
        )
    """, (tenant, tenant))
    auto_count = persons_in_flat[0][0] if persons_in_flat and persons_in_flat[0][0] else 1

    st.divider()
    tenants = st.number_input("Tenants in flat", value=int(auto_count), min_value=1)
    if auto_count > 1:
        st.caption(f"ℹ️ Auto-detected {auto_count} active tenants sharing the same flat.")

    # ── Tenant contract reference ──────────────────────────────────
    # Fetched once; each utility section intersects its own billing
    # period with these dates independently.
    st.divider()
    contract_row = fetch("""
        SELECT c.start_date, c.end_date
        FROM contracts c
        WHERE c.tenant_id = ?
        ORDER BY c.start_date DESC
        LIMIT 1
    """, (tenant_choice[0],))

    if not contract_row:
        st.warning("No contract found for this tenant.")
        st.stop()

    c_start_str, c_end_str = contract_row[0]
    contract_start = date.fromisoformat(c_start_str)
    contract_end   = (date.fromisoformat(c_end_str)
                      if c_end_str and c_end_str != 'None'
                      else None)
    contract_end_display = (
        contract_end.strftime("%d.%m.%Y") if contract_end else "unbefristet"
    )
    st.info(
        f"**Tenant contract:**  "
        f"{contract_start.strftime('%d.%m.%Y')} — {contract_end_display}  \n"
        "Each utility's billing period will be intersected with these dates "
        "to determine the tenant's effective share."
    )

    # ── Cost type selection ────────────────────────────────────────
    st.divider()
    st.subheader("Select Cost Types to Include")
    include_strom = st.checkbox("Strom (Electricity)")
    include_gas   = st.checkbox("Gas")
    include_bk    = st.checkbox("Betriebskosten (Operating costs)")

    strom_data = gas_data = bk_data = None

    # ── Helper: intersect a utility billing period with the contract ──
    def _effective(bill_start, bill_end):
        """
        Returns (eff_start, eff_end) clamped to the tenant's contract,
        or None if there is no overlap.
        """
        c_end = contract_end if contract_end else bill_end
        eff_s = max(bill_start, contract_start)
        eff_e = min(bill_end, c_end)
        return (eff_s, eff_e) if eff_s <= eff_e else None

    # ── Strom ──────────────────────────────────────────────────────
    if include_strom:
        st.subheader("Strom")
        col1, col2 = st.columns(2)
        with col1:
            strom_bill_start = st.date_input(
                "Strom billing period start",
                value=date.today().replace(month=1, day=1),
                min_value=date.today() - timedelta(days=365 * 20),
                key="strom_start"
            )
        with col2:
            strom_bill_end = st.date_input(
                "Strom billing period end",
                value=date.today().replace(month=12, day=31),
                key="strom_end"
            )
        strom_eff = _effective(strom_bill_start, strom_bill_end)
        if strom_eff is None:
            st.warning("Tenant's contract does not overlap with the Strom billing period.")
        else:
            s_eff_start_auto, s_eff_end_auto = strom_eff
            _strom_bill_key = (strom_bill_start, strom_bill_end)
            if st.session_state.get("_strom_bill_key") != _strom_bill_key:
                st.session_state["strom_eff_start"] = s_eff_start_auto
                st.session_state["strom_eff_end"]   = s_eff_end_auto
                st.session_state["_strom_bill_key"] = _strom_bill_key
            st.caption("Tenant's effective period (auto-detected, editable):")
            col1, col2 = st.columns(2)
            with col1:
                s_eff_start = st.date_input("Effective start",
                                            min_value=date.today() - timedelta(days=365*20),
                                            key="strom_eff_start")
            with col2:
                s_eff_end = st.date_input("Effective end", key="strom_eff_end")
            s_eff_days = (s_eff_end - s_eff_start).days
            st.caption(f"{s_eff_days} days")
            strom_limit_per_month = st.number_input(
                "Electricity prepayment per month (€)", min_value=0.0, key="strom_limit"
            )
            strom_cost = st.number_input(
                "Total electricity cost flat for billing period (€)", min_value=0.0, key="strom_cost"
            )
            strom_bill_days = max(1, (strom_bill_end - strom_bill_start).days)
            _, strom_limit, strom_nach = strom_calc(
                strom_cost, tenants, strom_bill_days, s_eff_days,
                limit_per_month=strom_limit_per_month
            )
            strom_data = {
                "bill_period": (f"{strom_bill_start.strftime('%d.%m.%Y')} – "
                                f"{strom_bill_end.strftime('%d.%m.%Y')}"),
                "bill_days": strom_bill_days,
                "period": (f"{s_eff_start.strftime('%d.%m.%Y')} – "
                           f"{s_eff_end.strftime('%d.%m.%Y')}"),
                "days": s_eff_days,
                "cost": strom_cost,
                "limit": strom_limit,
                "nach": strom_nach,
                "monthly_limit": strom_limit_per_month,
                "num_tenants": int(tenants),
            }

    # ── Gas ────────────────────────────────────────────────────────
    if include_gas:
        st.subheader("Gas")
        col1, col2 = st.columns(2)
        with col1:
            gas_bill_start = st.date_input(
                "Gas billing period start",
                value=date.today().replace(month=1, day=1),
                min_value=date.today() - timedelta(days=365 * 20),
                key="gas_start"
            )
        with col2:
            gas_bill_end = st.date_input(
                "Gas billing period end",
                value=date.today().replace(month=12, day=31),
                key="gas_end"
            )
        gas_eff = _effective(gas_bill_start, gas_bill_end)
        if gas_eff is None:
            st.warning("Tenant's contract does not overlap with the Gas billing period.")
        else:
            g_eff_start_auto, g_eff_end_auto = gas_eff
            _gas_bill_key = (gas_bill_start, gas_bill_end)
            if st.session_state.get("_gas_bill_key") != _gas_bill_key:
                st.session_state["gas_eff_start"] = g_eff_start_auto
                st.session_state["gas_eff_end"]   = g_eff_end_auto
                st.session_state["_gas_bill_key"] = _gas_bill_key
            st.caption("Tenant's effective period (auto-detected, editable):")
            col1, col2 = st.columns(2)
            with col1:
                g_eff_start = st.date_input("Effective start",
                                            min_value=date.today() - timedelta(days=365*20),
                                            key="gas_eff_start")
            with col2:
                g_eff_end = st.date_input("Effective end", key="gas_eff_end")
            g_eff_days = (g_eff_end - g_eff_start).days
            st.caption(f"{g_eff_days} days")
            gas_limit_per_month = st.number_input(
                "Gas prepayment per month (€)", min_value=0.0, key="gas_limit"
            )
            gas_cost = st.number_input(
                "Total gas cost flat for billing period (€)", min_value=0.0, key="gas_cost"
            )
            gas_bill_days = max(1, (gas_bill_end - gas_bill_start).days)
            _, gas_limit, gas_nach = gas_calc(
                gas_cost, tenants, gas_bill_days, g_eff_days,
                limit_per_month=gas_limit_per_month
            )
            gas_data = {
                "bill_period": (f"{gas_bill_start.strftime('%d.%m.%Y')} – "
                                f"{gas_bill_end.strftime('%d.%m.%Y')}"),
                "bill_days": gas_bill_days,
                "period": (f"{g_eff_start.strftime('%d.%m.%Y')} – "
                           f"{g_eff_end.strftime('%d.%m.%Y')}"),
                "days": g_eff_days,
                "cost": gas_cost,
                "limit": gas_limit,
                "nach": gas_nach,
                "monthly_limit": gas_limit_per_month,
                "num_tenants": int(tenants),
            }

    # ── Betriebskosten ─────────────────────────────────────────────
    if include_bk:
        st.subheader("Betriebskosten")

        _month_labels = {i: date(2000, i, 1).strftime("%B") for i in range(1, 13)}
        _year_opts    = list(range(date.today().year + 1, date.today().year - 20, -1))
        _prev_yr_idx  = next((i for i, y in enumerate(_year_opts)
                               if y == date.today().year - 1), 0)

        # Billing period — whole months
        st.caption("Billing period (month / year):")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            bk_s_month = st.selectbox("Start month", list(_month_labels.keys()),
                                       format_func=lambda m: _month_labels[m],
                                       index=0, key="bk_s_month")
        with col2:
            bk_s_year  = st.selectbox("Start year", _year_opts,
                                       index=_prev_yr_idx, key="bk_s_year")
        with col3:
            bk_e_month = st.selectbox("End month", list(_month_labels.keys()),
                                       format_func=lambda m: _month_labels[m],
                                       index=11, key="bk_e_month")
        with col4:
            bk_e_year  = st.selectbox("End year", _year_opts,
                                       index=_prev_yr_idx, key="bk_e_year")

        bk_bill_start = date(bk_s_year, bk_s_month, 1)
        bk_bill_end   = date(bk_e_year, bk_e_month,
                             calendar.monthrange(bk_e_year, bk_e_month)[1])

        bk_eff = _effective(bk_bill_start, bk_bill_end)
        if bk_eff is None:
            st.warning("Tenant's contract does not overlap with the BK billing period.")
        else:
            b_auto_start, b_auto_end = bk_eff

            # Reset effective period selectors when billing period changes
            _bk_bill_key = (bk_s_month, bk_s_year, bk_e_month, bk_e_year)
            if st.session_state.get("_bk_bill_key") != _bk_bill_key:
                st.session_state["bk_eff_s_month"] = b_auto_start.month
                st.session_state["bk_eff_s_year"]  = b_auto_start.year
                st.session_state["bk_eff_e_month"] = b_auto_end.month
                st.session_state["bk_eff_e_year"]  = b_auto_end.year
                st.session_state["_bk_bill_key"]   = _bk_bill_key

            # Effective period — auto-detected, editable as month/year
            st.caption("Tenant's effective period (auto-detected, editable):")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                be_s_month = st.selectbox("Eff. start month", list(_month_labels.keys()),
                                           format_func=lambda m: _month_labels[m],
                                           key="bk_eff_s_month")
            with col2:
                be_s_year  = st.selectbox("Eff. start year", _year_opts,
                                           key="bk_eff_s_year")
            with col3:
                be_e_month = st.selectbox("Eff. end month", list(_month_labels.keys()),
                                           format_func=lambda m: _month_labels[m],
                                           key="bk_eff_e_month")
            with col4:
                be_e_year  = st.selectbox("Eff. end year", _year_opts,
                                           key="bk_eff_e_year")

            b_eff_months = max(1, (be_e_year - be_s_year) * 12
                                  + (be_e_month - be_s_month) + 1)
            st.caption(f"{b_eff_months} month{'s' if b_eff_months != 1 else ''}")

            bk_limit_per_month = st.number_input(
                "Betriebskosten prepayment per month (€)", min_value=0.0, key="bk_limit"
            )
            bk_cost = st.number_input(
                "Total Betriebskosten for billing period (€)", min_value=0.0, key="bk_cost"
            )
            _, bk_period_cost, bk_limit, bk_nach = betriebskosten_calc(
                bk_cost, tenants, b_eff_months, bk_bill_start, bk_bill_end,
                limit_per_month=bk_limit_per_month
            )
            b_eff_start_date = date(be_s_year, be_s_month, 1)
            b_eff_end_date   = date(be_e_year, be_e_month,
                                    calendar.monthrange(be_e_year, be_e_month)[1])
            bk_num_months = max(1, (bk_e_year - bk_s_year) * 12
                                   + (bk_e_month - bk_s_month) + 1)
            bk_data = {
                "bill_period": (f"{bk_bill_start.strftime('%d.%m.%Y')} – "
                                f"{bk_bill_end.strftime('%d.%m.%Y')}"),
                "num_months": bk_num_months,
                "period": (f"{b_eff_start_date.strftime('%d.%m.%Y')} – "
                           f"{b_eff_end_date.strftime('%d.%m.%Y')}"),
                "months": int(b_eff_months),
                "total_cost": bk_cost,
                "cost": bk_period_cost,
                "limit": bk_limit,
                "nach": bk_nach,
                "monthly_limit": bk_limit_per_month,
                "num_tenants": int(tenants),
            }

    if st.button("Generate PDF"):
        if not any([strom_data, gas_data, bk_data]):
            st.warning("Please select at least one cost type.")
        else:
            file = invoice_pdf(
                tenant, address,
                landlord_name=landlord_name,
                gender=gender,
                signature_path=sig_path if Path(sig_path).exists() else None,
                strom=strom_data,
                gas=gas_data,
                bk=bk_data,
            )
            with open(file, "rb") as f:
                st.download_button("Download", f, file_name=file)


elif menu == "Mahnung Generator":

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
