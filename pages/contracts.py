import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import fetch, execute


def show():
    st.header("Tenant Contracts")

    # ── Existing Contracts table (always visible) ──────────────────
    contract_data = fetch("""
        SELECT c.id, t.name, a.name, c.rent, c.start_date, c.end_date
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        ORDER BY c.start_date DESC
    """)

    if contract_data:
        df = pd.DataFrame(contract_data,
                          columns=["ID", "Tenant", "Apartment", "Rent", "Start Date", "End Date"])

        def highlight(row):
            end = row["End Date"]
            if not end or end == "None":
                return [""] * len(row)
            try:
                d = date.fromisoformat(end)
                if d < date.today():
                    return ["background-color: #c0392b; color: white"] * len(row)
                elif (d - date.today()).days <= 90:
                    return ["background-color: #e67e22; color: white"] * len(row)
            except ValueError:
                pass
            return [""] * len(row)

        st.dataframe(df.style.apply(highlight, axis=1), width="stretch", hide_index=True)
        st.caption("🔴 Expired &nbsp;&nbsp; 🟡 Expiring within 90 days")
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
            cid, _, _, c_rent, c_start, c_end = c_choice

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

        # ── Terminate Contract ─────────────────────────────────────
        with st.expander("Terminate Contract (Move-out)"):
            active = [r for r in contract_data
                      if not r[5] or r[5] == "None" or r[5] >= str(date.today())]
            if active:
                to_term = st.selectbox("Select active contract", active,
                                       format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                                       key="terminate_select")
                moveout_date = st.date_input("Move-out date", value=date.today(), key="move_out_date")
                if st.button("Terminate Contract", key="btn_terminate"):
                    execute("UPDATE contracts SET end_date=? WHERE id=?",
                            (str(moveout_date), to_term[0]))
                    st.success(f"{to_term[1]} terminated on {moveout_date}.")
                    st.rerun()
            else:
                st.info("No active contracts to terminate.")

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
