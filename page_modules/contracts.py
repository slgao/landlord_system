import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import fetch, execute
from currencies import CURRENCY_LIST, CURRENCY_LABELS, sym, fmt


def show():
    st.header("Tenant Contracts")

    # ── Existing Contracts table (always visible) ──────────────────
    # col index: 0=id, 1=tenant, 2=apt, 3=rent, 4=start, 5=end, 6=terminated, 7=currency
    contract_data = fetch("""
        SELECT c.id, t.name, a.name, c.rent, c.start_date, c.end_date,
               COALESCE(c.terminated, 0), COALESCE(c.currency, 'EUR')
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
                                   "Start Date", "End Date", "Terminated", "Currency"])
        df["Status"]     = df.apply(status_label, axis=1)
        df["Terminated"] = df["Terminated"].apply(lambda x: "Yes" if x else "")
        df["Rent"] = df.apply(lambda r: fmt(r["Rent"], r["Currency"]), axis=1)
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
            col_cur, col_rent = st.columns([1, 2])
            with col_cur:
                new_c_currency = st.selectbox(
                    "Currency", CURRENCY_LIST,
                    format_func=lambda c: CURRENCY_LABELS[c],
                    key="new_c_currency",
                )
            with col_rent:
                rent = st.number_input(f"Monthly Rent ({sym(new_c_currency)})", value=650.0, key="new_c_rent")
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
                           (tenant_id, apartment_id, rent, start_date, end_date, currency)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (tenant_choice[0], apartment_choice[0], rent,
                         str(move_in), str(move_out) if move_out else None, new_c_currency)
                    )
                    st.success("Contract created.")
                    st.rerun()

    if contract_data:
        # ── Edit Contract ──────────────────────────────────────────
        with st.expander("Edit Contract"):
            c_choice = st.selectbox("Select contract", contract_data,
                                    format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                                    key="contract_edit")
            cid, _, _, c_rent, c_start, c_end, c_term, c_currency = c_choice

            apts_all  = fetch("SELECT id, name FROM apartments")
            apt_ids   = [a[0] for a in apts_all]
            c_apt_id  = fetch("SELECT apartment_id FROM contracts WHERE id=?", (cid,))[0][0]
            apt_index = apt_ids.index(c_apt_id) if c_apt_id in apt_ids else 0

            col1, col2 = st.columns(2)
            with col1:
                edit_apt  = st.selectbox("Apartment", apts_all, format_func=lambda x: x[1],
                                         index=apt_index, key=f"cedit_apt_{cid}")
                cur_idx = CURRENCY_LIST.index(c_currency) if c_currency in CURRENCY_LIST else 0
                edit_currency = st.selectbox(
                    "Currency", CURRENCY_LIST, index=cur_idx,
                    format_func=lambda c: CURRENCY_LABELS[c],
                    key=f"cedit_currency_{cid}",
                )
                edit_rent = st.number_input(f"Monthly Rent ({sym(edit_currency)})", value=float(c_rent),
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
                execute(
                    "UPDATE contracts SET apartment_id=?, rent=?, start_date=?, end_date=?, currency=? WHERE id=?",
                    (edit_apt[0], edit_rent, str(edit_start),
                     str(edit_end) if edit_end else None, edit_currency, cid),
                )
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
            kaution_overview = fetch("""
                SELECT c.id, t.name, a.name,
                       c.kaution_amount, c.kaution_paid_date,
                       COALESCE((SELECT SUM(amount) FROM kaution_deductions
                                  WHERE contract_id = c.id), 0) AS deducted,
                       c.kaution_returned_date, c.kaution_returned_amount,
                       COALESCE(c.kaution_currency, 'EUR')
                FROM contracts c
                JOIN tenants t ON c.tenant_id = t.id
                JOIN apartments a ON c.apartment_id = a.id
                ORDER BY c.start_date DESC
            """)

            def _balance(row):
                amt, deducted, ret = row[3] or 0.0, row[5] or 0.0, row[7]
                if ret is not None:
                    return 0.0
                return float(amt) - float(deducted)

            df_k = pd.DataFrame([
                (r[0], r[1], r[2],
                 fmt(float(r[3] or 0), r[8]), r[4],
                 fmt(float(r[5] or 0), r[8]), fmt(_balance(r), r[8]),
                 r[6], fmt(float(r[7] or 0), r[8]) if r[7] is not None else "")
                for r in kaution_overview
            ], columns=["Contract ID", "Tenant", "Apartment",
                        "Kaution", "Paid Date", "Deducted", "Open Balance",
                        "Returned Date", "Returned"])
            st.dataframe(df_k, width="stretch", hide_index=True)

            st.markdown("---")
            k_contract = st.selectbox("Contract", contract_data,
                                      format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}",
                                      key="kaution_contract")
            cid = k_contract[0]

            current = fetch(
                "SELECT kaution_amount, kaution_paid_date, "
                "kaution_returned_date, kaution_returned_amount, "
                "COALESCE(kaution_currency, 'EUR') "
                "FROM contracts WHERE id=?",
                (cid,)
            )[0]
            cur_amount = float(current[0]) if current[0] is not None else 0.0
            cur_paid   = current[1]
            cur_ret_d  = current[2]
            cur_ret_a  = float(current[3]) if current[3] is not None else None
            k_currency = current[4]

            deductions = fetch(
                "SELECT id, date, amount, category, reason "
                "FROM kaution_deductions WHERE contract_id=? ORDER BY date, id",
                (cid,)
            )
            total_deducted = sum(float(d[2] or 0) for d in deductions)
            settled = cur_ret_d is not None
            balance = 0.0 if settled else cur_amount - total_deducted

            m1, m2, m3 = st.columns(3)
            m1.metric("Kaution received", fmt(cur_amount, k_currency))
            m2.metric("Deductions", fmt(total_deducted, k_currency))
            m3.metric(
                "Open balance" if not settled else "Open balance (settled)",
                fmt(balance, k_currency),
            )
            if settled:
                st.caption(
                    f"Kaution closed: returned **{fmt(cur_ret_a or 0.0, k_currency)}** on **{cur_ret_d}**. "
                    "Clear the return record below to add more deductions."
                )

            # ── Record / update received Kaution ──
            st.markdown("**1. Record / update received Kaution**")
            col1, col2, col3 = st.columns([1, 2, 2])
            with col1:
                k_cur_idx = CURRENCY_LIST.index(k_currency) if k_currency in CURRENCY_LIST else 0
                k_new_currency = st.selectbox(
                    "Currency",
                    CURRENCY_LIST,
                    index=k_cur_idx,
                    format_func=lambda c: CURRENCY_LABELS[c],
                    key=f"k_currency_{cid}",
                )
            with col2:
                k_amount = st.number_input(
                    f"Kaution amount ({sym(k_new_currency)})", min_value=0.0,
                    value=cur_amount, key=f"k_amount_{cid}"
                )
            with col3:
                k_paid = st.date_input(
                    "Date received",
                    value=date.fromisoformat(cur_paid) if cur_paid else date.today(),
                    key=f"k_paid_{cid}"
                )
            if st.button("Save received Kaution", key=f"btn_save_kaution_{cid}"):
                execute(
                    "UPDATE contracts SET kaution_amount=?, kaution_paid_date=?, kaution_currency=? WHERE id=?",
                    (k_amount, str(k_paid), k_new_currency, cid)
                )
                st.success("Kaution received recorded.")
                st.rerun()

            # ── Deductions ledger ──
            st.markdown("**2. Deductions (e.g. NK Nachzahlung verrechnet, Schaden, Reinigung)**")
            if deductions:
                df_d = pd.DataFrame(deductions,
                                    columns=["ID", "Date", "Amount (€)", "Category", "Reason"])
                st.dataframe(df_d, width="stretch", hide_index=True)

                del_choice = st.selectbox(
                    "Delete deduction", deductions,
                    format_func=lambda d: f"#{d[0]} — {d[1]} — {d[3] or ''} — {fmt(float(d[2] or 0), k_currency)}",
                    key=f"k_del_choice_{cid}"
                )
                if st.button("Delete selected deduction", key=f"btn_k_del_{cid}"):
                    execute("DELETE FROM kaution_deductions WHERE id=?", (del_choice[0],))
                    st.success("Deduction removed.")
                    st.rerun()
            else:
                st.caption("No deductions yet.")

            st.markdown("**Add deduction**")
            d1, d2, d3 = st.columns([1, 1, 2])
            with d1:
                d_date = st.date_input("Date", value=date.today(), key=f"k_d_date_{cid}")
                d_amount = st.number_input(f"Amount ({sym(k_currency)})", min_value=0.0,
                                           step=10.0, key=f"k_d_amount_{cid}")
            with d2:
                d_category = st.selectbox(
                    "Category",
                    ["NK Nachzahlung", "Schaden", "Reinigung", "Mietrückstand", "Sonstiges"],
                    key=f"k_d_category_{cid}"
                )
            with d3:
                d_reason = st.text_area("Reason / note", height=80, key=f"k_d_reason_{cid}",
                                        placeholder="z.B. Nebenkostenabrechnung 2024 verrechnet")
            if st.button("Add deduction", key=f"btn_k_add_{cid}"):
                if settled:
                    st.warning(
                        "Kaution is already marked as returned. "
                        "Clear the return record below before adding more deductions."
                    )
                elif d_amount <= 0:
                    st.warning("Enter a positive amount.")
                elif d_amount > balance:
                    st.warning(
                        f"Deduction ({fmt(d_amount, k_currency)}) exceeds open balance "
                        f"({fmt(balance, k_currency)}). Adjust the amount or increase the Kaution."
                    )
                else:
                    execute(
                        "INSERT INTO kaution_deductions "
                        "(contract_id, date, amount, category, reason) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (cid, str(d_date), d_amount, d_category, d_reason or None)
                    )
                    st.success("Deduction recorded.")
                    st.rerun()

            # ── Return remaining balance to tenant ──
            st.markdown("**3. Return remaining balance to tenant**")
            if cur_ret_d:
                st.info(
                    f"Already returned **{fmt(cur_ret_a or 0.0, k_currency)}** on **{cur_ret_d}**. "
                    "Use the button below to clear and re-record."
                )
                if st.button("Clear return record", key=f"btn_k_clear_ret_{cid}"):
                    execute(
                        "UPDATE contracts SET kaution_returned_date=NULL, "
                        "kaution_returned_amount=NULL WHERE id=?",
                        (cid,)
                    )
                    st.rerun()
            else:
                r1, r2 = st.columns(2)
                with r1:
                    r_date = st.date_input("Return date", value=date.today(),
                                           key=f"k_r_date_{cid}")
                with r2:
                    r_amount = st.number_input(
                        f"Returned amount ({sym(k_currency)})", min_value=0.0,
                        value=max(balance, 0.0), step=10.0,
                        key=f"k_r_amount_{cid}",
                        help="Defaults to the open balance. Override if you returned a different amount."
                    )
                if st.button("Mark Kaution returned", key=f"btn_k_return_{cid}"):
                    if r_amount > balance + 1e-9:
                        st.warning(
                            f"Returned amount ({fmt(r_amount, k_currency)}) exceeds the open "
                            f"balance ({fmt(balance, k_currency)}). Either lower the amount, "
                            "remove a deduction, or increase the recorded Kaution."
                        )
                    else:
                        execute(
                            "UPDATE contracts SET kaution_returned_date=?, "
                            "kaution_returned_amount=? WHERE id=?",
                            (str(r_date), r_amount, cid)
                        )
                        st.success(f"Returned {fmt(r_amount, k_currency)} on {r_date}.")
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
                st.dataframe(df_ct, hide_index=True)

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
