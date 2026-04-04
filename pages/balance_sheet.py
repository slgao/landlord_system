import streamlit as st
import pandas as pd
import calendar
from datetime import date
from db import fetch


def show():
    st.header("Balance Sheet")

    year = st.selectbox("Year", list(range(date.today().year, date.today().year - 6, -1)))
    y = int(year)

    properties = fetch("SELECT id, name FROM properties")
    if not properties:
        st.warning("No properties found.")
        return

    for prop_id, prop_name in properties:
        st.subheader(f"🏠 {prop_name}")

        max_month    = date.today().month if y == date.today().year else 12
        month_labels = [date(y, m, 1).strftime("%b %Y") for m in range(1, max_month + 1)]
        rows         = []
        total_income = total_costs = 0.0

        for m in range(1, max_month + 1):
            m_start = f"{y}-{m:02d}-01"
            m_end   = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"

            income = fetch("""
                SELECT COALESCE(SUM(p.amount), 0)
                FROM payments p
                JOIN contracts c ON p.contract_id = c.id
                JOIN apartments a ON c.apartment_id = a.id
                WHERE a.property_id=? AND p.payment_date BETWEEN ? AND ?
            """, (prop_id, m_start, m_end))[0][0]

            cost_rows = fetch("""
                SELECT fc.amount, fc.frequency, fc.valid_from, fc.valid_to
                FROM flat_costs fc
                JOIN apartments a ON fc.apartment_id = a.id
                WHERE a.property_id=?
                AND fc.valid_from <= ?
                AND (fc.valid_to IS NULL OR fc.valid_to = 'None' OR fc.valid_to >= ?)
            """, (prop_id, m_end, m_start))

            costs = 0.0
            for amt, freq, vf, _ in cost_rows:
                if freq == "monthly":
                    costs += amt
                elif freq == "annual":
                    costs += amt / 12
                elif vf and vf[:7] == f"{y}-{m:02d}":
                    costs += amt

            net           = income - costs
            total_income += income
            total_costs  += costs
            rows.append({
                "Month":       month_labels[m - 1],
                "Income (€)":  round(income, 2),
                "Costs (€)":   round(costs, 2),
                "Net (€)":     round(net, 2),
            })

        def color_net(val):
            return "color: green" if val >= 0 else "color: red"

        st.dataframe(pd.DataFrame(rows).style.map(color_net, subset=["Net (€)"]),
                     width="stretch", hide_index=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Income", f"€ {total_income:,.2f}")
        col2.metric("Total Costs",  f"€ {total_costs:,.2f}")
        col3.metric("Annual Net",   f"€ {total_income - total_costs:,.2f}")
        st.divider()
