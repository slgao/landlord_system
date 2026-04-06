import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import fetch, execute


def show():
    st.header("Tenant Contracts")

    # ── Existing Contracts table (always visible) ──────────────────
    # col index: 0=id, 1=tenant, 2=apt, 3=rent, 4=start, 5=end, 6=terminated
    contract_data = fetch("""
        SELECT c.id, t.name, a.name, c.rent, c.start_date, c.end_date,
               COALESCE(c.terminated, 0)
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        ORDER BY c.start_date DESC
    """)

    if contract_data:
        today_str = str(date.today())

        def status_label(row):
            end, term = row["End Date"], row["Terminated"]
            if term:
                return "Moved out"
            if not end or end == "None":
                return "Active"
            try:
                d = date.fromisoformat(end)
                days = (d - date.today()).days
                if days < 0:
                    return "Expired"
                elif days <= 90:
                    return "Expiring soon"
            except ValueError:
                pass
            return "Active"

        def highlight(row):
            s = row["Status"]
            if s == "Moved out":
                return ["color: #8395a7"] * len(row)
            if s == "Expired":
                return ["background-color: #c0392b; color: white"] * len(row)
            if s == "Expiring soon":
                return ["background-color: #e67e22; color: white"] * len(row)
            return [""] * len(row)

        df = pd.DataFrame(contract_data,
                          columns=["ID", "Tenant", "Apartment", "Rent",
                                   "Start Date", "End Date", "Terminated"])
        df["Status"]     = df.apply(status_label, axis=1)
        df["Terminated"] = df["Terminated"].apply(lambda x: "Yes" if x else "")
        df = df[["ID", "Tenant", "Apartment", "Rent", "Start Date", "End Date", "Status"]]

        st.dataframe(df.style.apply(highlight, axis=1), width="stretch", hide_index=True)
        st.caption("🔴 Expired – needs renewal &nbsp;&nbsp; 🟠 Expiring within 90 days &nbsp;&nbsp; ⬜ Moved out (closed)")
    else:
        st.info("No contracts yet.")

    st.divider()

    # ── Create New Contract ────────────────────────────────────────
    with st.expander("Create New Contract"):
        tenants    = fetch("SELECT id, name FROM tenants")
        apartments = fetch("SELECT id, name FROM apartments")
        if not tenants or not apartments:
            st.warning("Please create tenants and apartments first.")
        else:
            tenant_choice    = st.selectbox("Tenant",    tenants,    format_func=lambda x: x[1], key="new_c_tenant")
            apartment_choice = st.selectbox("Apartment", apartments, format_func=lambda x: x[1], key="new_c_apt")
            rent = st.number_input("Monthly Rent (€)", value=650.0, key="new_c_rent")
            col1, col2 = st.columns(2)
            with col1:
                move_in = st.date_input("Move-in date",
                                        min_value=date.today() - timedelta(days=365 * 20),
                                        key="new_c_movein")
            is_limited = st.checkbox("Fixed Term", key="new_c_limited")
            move_out = None
            if is_limited:
                with col2:
                    move_out = st.date_input("Move-out date", key="new_c_moveout")

            if st.button("Create Contract", key="btn_create_contract"):
                overlap = fetch("""
                    SELECT t.name FROM contracts c
                    JOIN tenants t ON c.tenant_id = t.id
                    WHERE c.apartment_id = ?
                    AND COALESCE(c.terminated, 0) = 0
                    AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= ?)
                    AND c.start_date <= ?
                """, (apartment_choice[0], str(move_in),
                      str(move_out) if move_out else "9999-12-31"))
                if overlap:
                    st.warning(f"⚠️ Apartment already occupied by **{overlap[0][0]}** in this period.")
                else:
                    execute(
                        """INSERT INTO contracts
                           (tenant_id, apartment_id, rent, start_date, end_date)
                           VALUES (?, ?, ?, ?, ?)""",
                        (tenant_choice[0], apartment_choice[0], rent,
                         str(move_in), str(move_out) if move_out else None)
                    )
                    st.success("Contract created.")
                    st.rerun()

    if contract_data:
        # ── Edit Contract ──────────────────────────────────────────
        with st.expander("Edit Contract"):
            c_choice = st.selectbox("Select contract", contract_data,
                                    format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                                    key="contract_edit")
            cid, _, _, c_rent, c_start, c_end, c_term = c_choice

            apts_all  = fetch("SELECT id, name FROM apartments")
            apt_ids   = [a[0] for a in apts_all]
            c_apt_id  = fetch("SELECT apartment_id FROM contracts WHERE id=?", (cid,))[0][0]
            apt_index = apt_ids.index(c_apt_id) if c_apt_id in apt_ids else 0

            col1, col2 = st.columns(2)
            with col1:
                edit_apt  = st.selectbox("Apartment", apts_all, format_func=lambda x: x[1],
                                         index=apt_index, key=f"cedit_apt_{cid}")
                edit_rent = st.number_input("Monthly Rent (€)", value=float(c_rent),
                                            key=f"cedit_rent_{cid}")
            with col2:
                edit_start   = st.date_input("Start date", value=date.fromisoformat(c_start),
                                             min_value=date.today() - timedelta(days=365 * 20),
                                             key=f"cedit_start_{cid}")
                edit_limited = st.checkbox("Fixed Term", value=bool(c_end and c_end != "None"),
                                           key=f"cedit_limited_{cid}")
                edit_end = None
                if edit_limited:
                    edit_end = st.date_input(
                        "End date",
                        value=date.fromisoformat(c_end) if c_end and c_end != "None" else date.today(),
                        key=f"cedit_end_{cid}"
                    )

            if st.button("Save Contract Changes", key="btn_save_contract"):
                execute("UPDATE contracts SET apartment_id=?, rent=?, start_date=?, end_date=? WHERE id=?",
                        (edit_apt[0], edit_rent, str(edit_start),
                         str(edit_end) if edit_end else None, cid))
                st.success("Contract updated.")
                st.rerun()

        # ── Terminate Contract (Move-out) ──────────────────────────
        with st.expander("Terminate Contract (Move-out)"):
            # Active = not yet terminated, end_date not yet past
            active = [r for r in contract_data
                      if not r[6]
                      and (not r[5] or r[5] == "None" or r[5] >= str(date.today()))]
            if active:
                to_term = st.selectbox("Select active contract", active,
                                       format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                                       key="terminate_select")
                moveout_date = st.date_input("Move-out date", value=date.today(), key="move_out_date")
                if st.button("Terminate Contract", key="btn_terminate"):
                    execute("UPDATE contracts SET end_date=?, terminated=1 WHERE id=?",
                            (str(moveout_date), to_term[0]))
                    st.success(f"{to_term[1]} marked as moved out on {moveout_date}.")
                    st.rerun()
            else:
                st.info("No active contracts to terminate.")

        # ── Handle Expired Contracts ───────────────────────────────
        with st.expander("Handle Expired Contracts"):
            st.caption(
                "These contracts have passed their end date and are flagged as needing attention. "
                "Choose what happened: close the contract if the tenant moved out, "
                "or reopen it if the tenant is still living there and a new agreement is pending."
            )
            expired = [r for r in contract_data
                       if not r[6]
                       and r[5] and r[5] != "None" and r[5] < str(date.today())]
            if expired:
                to_handle = st.selectbox(
                    "Select expired contract", expired,
                    format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}  (ended {x[5]})",
                    key="handle_expired_select"
                )
                action = st.radio(
                    "Action",
                    ["Close — tenant has moved out", "Reopen — tenant is still living there"],
                    key="handle_expired_action"
                )
                if st.button("Apply", key="btn_handle_expired"):
                    if action.startswith("Close"):
                        execute("UPDATE contracts SET terminated=1 WHERE id=?", (to_handle[0],))
                        st.success(f"Contract #{to_handle[0]} ({to_handle[1]}) closed.")
                    else:
                        execute("UPDATE contracts SET end_date=NULL WHERE id=?", (to_handle[0],))
                        st.success(f"Contract #{to_handle[0]} ({to_handle[1]}) reopened — end date cleared.")
                    st.rerun()
            else:
                st.info("No expired contracts need attention.")

        # ── Kaution (Deposit) ──────────────────────────────────────
        with st.expander("Kaution (Deposit)"):
            kaution_data = fetch("""
                SELECT c.id, t.name, a.name,
                       c.kaution_amount, c.kaution_paid_date,
                       c.kaution_returned_date, c.kaution_returned_amount
                FROM contracts c
                JOIN tenants t ON c.tenant_id = t.id
                JOIN apartments a ON c.apartment_id = a.id
            """)
            df_k = pd.DataFrame(kaution_data,
                                columns=["Contract ID", "Tenant", "Apartment",
                                         "Kaution (€)", "Paid Date", "Returned Date", "Returned (€)"])
            st.dataframe(df_k, width="stretch", hide_index=True)

            st.markdown("**Record / Update Kaution**")
            k_contract = st.selectbox("Contract", contract_data,
                                      format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                                      key="kaution_contract")
            col1, col2 = st.columns(2)
            with col1:
                k_amount = st.number_input("Kaution amount (€)", min_value=0.0, key="k_amount")
                k_paid   = st.date_input("Date received", key="k_paid")
            with col2:
                k_returned     = st.date_input("Date returned (if applicable)", key="k_returned")
                k_returned_amt = st.number_input("Amount returned (€)", min_value=0.0, key="k_returned_amt")

            if st.button("Save Kaution", key="btn_kaution"):
                execute("""UPDATE contracts SET
                               kaution_amount=?, kaution_paid_date=?,
                               kaution_returned_date=?, kaution_returned_amount=?
                           WHERE id=?""",
                        (k_amount, str(k_paid),
                         str(k_returned) if k_returned_amt > 0 else None,
                         k_returned_amt if k_returned_amt > 0 else None,
                         k_contract[0]))
                st.success("Kaution saved.")
                st.rerun()

        # ── Co-Tenants ─────────────────────────────────────────────
        with st.expander("Co-Tenants"):
            st.caption(
                "Add additional occupants to a contract (e.g. partners, flatmates). "
                "Those marked **In Contract** appear in the address block and salutation of the PDF. "
                "Others (e.g. partners not on the lease) are stored for reference only."
            )
            ct_contract = st.selectbox(
                "Select contract", contract_data,
                format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                key="ct_contract_sel",
            )
            existing_ct = fetch(
                "SELECT id, name, gender, email, in_contract FROM co_tenants "
                "WHERE contract_id=? ORDER BY id",
                (ct_contract[0],)
            )
            if existing_ct:
                df_ct = pd.DataFrame(
                    existing_ct,
                    columns=["ID", "Name", "Gender", "Email", "In Contract"],
                )
                df_ct["In Contract"] = df_ct["In Contract"].apply(lambda x: "Yes" if x else "No")
                st.dataframe(df_ct, hide_index=True, use_container_width=True)

                to_del_ct = st.selectbox(
                    "Remove co-tenant", existing_ct,
                    format_func=lambda x: f"{x[1]} ({x[2]}){' — in contract' if x[4] else ''}",
                    key="ct_del_sel",
                )
                if st.button("Remove", key="btn_del_ct", type="primary"):
                    execute("DELETE FROM co_tenants WHERE id=?", (to_del_ct[0],))
                    st.success(f"Removed {to_del_ct[1]}.")
                    st.rerun()
            else:
                st.info("No co-tenants for this contract.")

            st.markdown("**Add co-tenant**")
            col1, col2 = st.columns(2)
            with col1:
                ct_name   = st.text_input("Name", key="ct_name_input",
                                          placeholder="e.g. Maria Müller")
                ct_email  = st.text_input("Email (optional)", key="ct_email_input",
                                          placeholder="e.g. maria@example.com")
            with col2:
                ct_gender      = st.selectbox("Gender", ["diverse", "female", "male"],
                                              key="ct_gender_input")
                ct_in_contract = st.toggle(
                    "In contract (Mitmieter)",
                    key="ct_in_contract_input",
                    help="Enable if this person is named on the rental contract. "
                         "They will appear in the Nebenkostenabrechnung PDF.",
                )
            if st.button("Add Co-Tenant", key="btn_add_ct"):
                if not ct_name.strip():
                    st.warning("Name is required.")
                else:
                    execute(
                        "INSERT INTO co_tenants (contract_id, name, gender, email, in_contract) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (ct_contract[0], ct_name.strip(), ct_gender,
                         ct_email.strip() or None, int(ct_in_contract)),
                    )
                    st.success(f"Added {ct_name.strip()}.")
                    st.rerun()

        # ── Delete Contract (last) ─────────────────────────────────
        with st.expander("Delete Contract"):
            to_del = st.selectbox("Select contract", contract_data,
                                  format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                                  key="contract_delete")
            st.warning("This permanently removes the contract and cannot be undone.")
            if st.button("Delete Contract", type="primary", key="btn_delete_contract"):
                execute("DELETE FROM contracts WHERE id=?", (to_del[0],))
                st.success(f"Contract #{to_del[0]} deleted.")
                st.rerun()
