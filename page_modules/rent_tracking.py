import streamlit as st
import pandas as pd
from datetime import date
from db import fetch, insert, execute


def show():
    st.header("Rent Payments")

    # ── Monthly Overview (always visible at top) ───────────────────
    st.subheader("Monthly Overview")
    today = date.today()
    selected_month = st.date_input("Select month", value=today.replace(day=1), format="YYYY-MM-DD")
    month_start = selected_month.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    monthly_payments = fetch("""
        SELECT p.name, a.name, t.name, pay.amount, pay.payment_date
        FROM payments pay
        JOIN contracts c ON pay.contract_id = c.id
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        WHERE pay.payment_date >= ? AND pay.payment_date < ?
        ORDER BY p.name, a.name, pay.payment_date
    """, (str(month_start), str(month_end)))

    if monthly_payments:
        df_monthly = pd.DataFrame(monthly_payments,
                                  columns=["Property", "Apartment", "Tenant", "Amount (€)", "Date"])
        st.dataframe(df_monthly, width="stretch", hide_index=True)
        st.metric("Total collected", f"€ {sum(r[3] for r in monthly_payments):,.2f}")
    else:
        st.info(f"No payments recorded for {month_start.strftime('%B %Y')}.")

    st.divider()

    # ── Payment History per Contract ───────────────────────────────
    contracts = fetch("""
        SELECT c.id, t.name, a.name
        FROM contracts c
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        ORDER BY t.name
    """)

    if not contracts:
        st.warning("No contracts found.")
        return

    st.subheader("Payment History")
    contract_choice = st.selectbox("Contract", contracts,
                                   format_func=lambda x: f"{x[1]} — {x[2]}")

    payments = fetch("""
        SELECT p.id, t.name, a.name, p.amount, p.payment_date
        FROM payments p
        JOIN contracts c ON p.contract_id = c.id
        JOIN tenants t ON c.tenant_id = t.id
        JOIN apartments a ON c.apartment_id = a.id
        WHERE p.contract_id = ?
        ORDER BY p.payment_date DESC
    """, (contract_choice[0],))

    if payments:
        df_pay = pd.DataFrame(payments, columns=["ID", "Tenant", "Apartment", "Amount (€)", "Date"])
        st.dataframe(df_pay, width="stretch", hide_index=True)
    else:
        st.info("No payments recorded for this contract.")

    st.divider()

    # ── Add Payment ────────────────────────────────────────────────
    with st.expander("Add Payment"):
        amount   = st.number_input("Payment amount (€)", value=650.0, key="pay_amount_new")
        pay_date = st.date_input("Payment date", key="pay_date_new")
        if st.button("Add Payment", key="btn_add_pay"):
            insert("payments", (contract_choice[0], amount, str(pay_date)))
            st.success("Payment recorded.")
            st.rerun()

    if payments:
        with st.expander("Edit Payment"):
            pay_to_edit = st.selectbox("Select payment", payments,
                                       format_func=lambda x: f"#{x[0]} — {x[3]:.2f} € on {x[4]}",
                                       key="pay_edit")
            col1, col2 = st.columns(2)
            with col1:
                new_amount = st.number_input("Amount (€)", value=float(pay_to_edit[3]),
                                             key=f"pay_amt_{pay_to_edit[0]}")
            with col2:
                new_date = st.date_input("Payment date",
                                         value=date.fromisoformat(pay_to_edit[4]),
                                         key=f"pay_date_{pay_to_edit[0]}")
            if st.button("Save Payment", key="btn_save_pay"):
                execute("UPDATE payments SET amount=?, payment_date=? WHERE id=?",
                        (new_amount, str(new_date), pay_to_edit[0]))
                st.success("Payment updated.")
                st.rerun()

        with st.expander("Delete Payment"):
            to_del = st.selectbox("Select payment", payments,
                                  format_func=lambda x: f"#{x[0]} — {x[3]:.2f} € on {x[4]}",
                                  key="pay_delete")
            st.warning("This will permanently delete the payment record.")
            if st.button("Delete Payment", type="primary", key="btn_del_pay"):
                execute("DELETE FROM payments WHERE id=?", (to_del[0],))
                st.success(f"Payment #{to_del[0]} deleted.")
                st.rerun()
