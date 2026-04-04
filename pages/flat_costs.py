import streamlit as st
import pandas as pd
from datetime import date
from itertools import groupby
from db import fetch, insert, execute


def show():
    st.header("Flat Costs")

    # ── Existing Costs grouped by property / flat (always visible) ─
    costs = fetch("""
        SELECT fc.id, p.name, a.name, a.flat, fc.cost_type, fc.amount, fc.frequency,
               fc.valid_from, fc.valid_to
        FROM flat_costs fc
        JOIN apartments a ON fc.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        ORDER BY p.name, a.flat, fc.cost_type
    """)

    if costs:
        _today = date.today()
        for (prop, flat), group in groupby(costs, key=lambda x: (x[1], x[3])):
            label = f"{prop} — {flat}" if flat else f"{prop} — (no flat)"
            st.markdown(f"**{label}**")
            group_rows = list(group)
            df_group = pd.DataFrame(
                [(r[0], r[4], r[5], r[6], r[7], r[8]) for r in group_rows],
                columns=["ID", "Type", "Amount (€)", "Frequency", "Valid From", "Valid To"]
            )
            st.dataframe(df_group, width="stretch", hide_index=True)

            # Monthly equivalent summary
            monthly_equiv = 0.0
            onetime_active = 0
            for r in group_rows:
                try:
                    from_ok = date.fromisoformat(r[7]) <= _today
                except (ValueError, TypeError):
                    from_ok = True
                try:
                    to_ok = not r[8] or r[8] == "None" or date.fromisoformat(r[8]) >= _today
                except (ValueError, TypeError):
                    to_ok = True
                if from_ok and to_ok:
                    if r[6] == "monthly":
                        monthly_equiv += r[5]
                    elif r[6] == "annual":
                        monthly_equiv += r[5] / 12
                    else:
                        onetime_active += 1
            note = f"  ·  +{onetime_active} one-time cost(s) active" if onetime_active else ""
            st.markdown(
                f"<div style='background:#2c3e50;border-left:4px solid #3a7fc1;"
                f"padding:6px 12px;border-radius:4px;margin-bottom:12px;'>"
                f"<span style='color:#9ec5e8;font-size:0.82em;'>Monthly total (currently active)</span><br>"
                f"<b style='font-size:1.1em;color:#ffffff;'>{monthly_equiv:.2f} €</b>"
                f"<span style='color:#8395a7;font-size:0.82em;'>{note}</span></div>",
                unsafe_allow_html=True
            )
            st.write("")
    else:
        st.info("No costs recorded yet.")

    st.divider()

    apartments = fetch("SELECT id, name, flat FROM apartments")

    with st.expander("Add Cost"):
        if not apartments:
            st.warning("No apartments found.")
        else:
            apt_choice = st.selectbox("Apartment", apartments,
                                      format_func=lambda x: f"{x[1]} ({x[2]})" if x[2] else x[1],
                                      key="fc_apt_new")
            col1, col2 = st.columns(2)
            with col1:
                type_opts    = ["Hausgeld", "Mortgage", "Grundsteuer",
                                "Strom Vorauszahlung", "Internet", "Other"]
                cost_type_sel = st.selectbox("Cost type", type_opts, key="fc_type_sel")
                cost_type     = (st.text_input("Custom type", key="fc_custom_type")
                                 if cost_type_sel == "Other" else cost_type_sel)
                amount        = st.number_input("Amount (€)", min_value=0.0, key="fc_amount_new")
            with col2:
                frequency      = st.selectbox("Frequency", ["monthly", "annual", "one-time"],
                                              key="fc_freq_new")
                valid_from     = st.date_input("Valid from", key="fc_from_new")
                valid_to_en    = st.checkbox("Set end date", key="fc_to_en_new")
                valid_to       = st.date_input("Valid to", key="fc_to_new") if valid_to_en else None

            if st.button("Add Cost", key="btn_add_cost"):
                insert("flat_costs", (apt_choice[0], cost_type, amount, frequency,
                                      str(valid_from), str(valid_to) if valid_to else None))
                st.success("Cost added.")
                st.rerun()

    if costs:
        all_costs = fetch("""
            SELECT fc.id, a.name, a.flat, fc.cost_type, fc.amount, fc.frequency,
                   fc.valid_from, fc.valid_to
            FROM flat_costs fc
            JOIN apartments a ON fc.apartment_id = a.id
            ORDER BY a.name, fc.cost_type
        """)

        with st.expander("Edit Cost"):
            type_opts = ["Hausgeld", "Mortgage", "Grundsteuer",
                         "Strom Vorauszahlung", "Internet", "Other"]
            freq_opts = ["monthly", "annual", "one-time"]
            cost_to_edit = st.selectbox(
                "Select cost", all_costs,
                format_func=lambda x: f"#{x[0]} — {x[1]} ({x[2]}) / {x[3]} ({x[5]})",
                key="cost_edit"
            )
            _, _, _, c_type, c_amt, c_freq, c_from, c_to = cost_to_edit
            col1, col2 = st.columns(2)
            with col1:
                edit_type_sel = st.selectbox("Cost type", type_opts,
                                             index=type_opts.index(c_type) if c_type in type_opts else 5,
                                             key=f"cedit_type_{cost_to_edit[0]}")
                edit_type     = (st.text_input("Custom type",
                                               value=c_type if c_type not in type_opts else "",
                                               key=f"cedit_custom_{cost_to_edit[0]}")
                                 if edit_type_sel == "Other" else edit_type_sel)
                edit_amount   = st.number_input("Amount (€)", value=float(c_amt), min_value=0.0,
                                                key=f"cedit_amt_{cost_to_edit[0]}")
            with col2:
                edit_freq  = st.selectbox("Frequency", freq_opts,
                                          index=freq_opts.index(c_freq) if c_freq in freq_opts else 0,
                                          key=f"cedit_freq_{cost_to_edit[0]}")
                edit_from  = st.date_input("Valid from", value=date.fromisoformat(c_from),
                                           key=f"cedit_from_{cost_to_edit[0]}")
                edit_to_en = st.checkbox("Set end date", value=bool(c_to and c_to != "None"),
                                         key=f"cedit_to_en_{cost_to_edit[0]}")
                edit_to    = (st.date_input("Valid to",
                                            value=date.fromisoformat(c_to) if c_to and c_to != "None" else date.today(),
                                            key=f"cedit_to_{cost_to_edit[0]}")
                              if edit_to_en else None)

            if st.button("Save Cost", key="btn_save_cost"):
                execute("""UPDATE flat_costs SET cost_type=?, amount=?, frequency=?,
                                                 valid_from=?, valid_to=? WHERE id=?""",
                        (edit_type, edit_amount, edit_freq, str(edit_from),
                         str(edit_to) if edit_to else None, cost_to_edit[0]))
                st.success("Cost updated.")
                st.rerun()

        with st.expander("Delete Cost"):
            to_del = st.selectbox("Select cost", all_costs,
                                  format_func=lambda x: f"#{x[0]} — {x[1]} / {x[3]} ({x[5]})",
                                  key="cost_delete")
            st.warning("This will permanently delete the cost entry.")
            if st.button("Delete Cost", type="primary", key="btn_del_cost"):
                execute("DELETE FROM flat_costs WHERE id=?", (to_del[0],))
                st.success("Cost deleted.")
                st.rerun()
