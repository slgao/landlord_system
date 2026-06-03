import streamlit as st
import pandas as pd
from datetime import date
from decimal import Decimal
from itertools import groupby
from db import fetch, insert, execute

_ZERO = Decimal("0")


def _monthly_equiv(amount, frequency):
    if frequency == "monthly":
        return amount
    elif frequency == "annual":
        return amount / 12
    return _ZERO


def _is_active(valid_from, valid_to, today):
    try:
        from_ok = date.fromisoformat(valid_from) <= today
    except (ValueError, TypeError):
        from_ok = True
    try:
        to_ok = not valid_to or valid_to == "None" or date.fromisoformat(valid_to) >= today
    except (ValueError, TypeError):
        to_ok = True
    return from_ok and to_ok


def show():
    st.header("Flat Costs")

    costs = fetch("""
        SELECT fc.id, p.name, a.name, a.flat, fc.cost_type, fc.amount, fc.frequency,
               fc.valid_from, fc.valid_to
        FROM flat_costs fc
        JOIN apartments a ON fc.apartment_id = a.id
        JOIN properties p ON a.property_id = p.id
        ORDER BY p.name, a.flat, fc.cost_type
    """)

    if not costs:
        st.info("No costs recorded yet.")
    else:
        today = date.today()
        grouped = {}
        for row in costs:
            key = (row[1], row[3] or "—")   # (property, flat)
            grouped.setdefault(key, []).append(row)

        # ── Grand summary table ────────────────────────────────────
        summary_rows = []
        grand_monthly = _ZERO
        for (prop, flat), rows in grouped.items():
            active_monthly = sum(
                (_monthly_equiv(r[5], r[6]) for r in rows if _is_active(r[7], r[8], today)),
                _ZERO,
            )
            onetime = sum(1 for r in rows
                          if r[6] == "one-time" and _is_active(r[7], r[8], today))
            grand_monthly += active_monthly
            summary_rows.append({
                "Property": prop,
                "Flat":     flat,
                "Active monthly (€)":  f"{active_monthly:.2f}",
                "Active annual  (€)":  f"{active_monthly * 12:.2f}",
                "One-time active": onetime,
                "Entries": len(rows),
            })

        df_summary = pd.DataFrame(summary_rows)
        st.subheader("Summary — all flats")
        st.dataframe(df_summary, hide_index=True)

        # Grand total metric row
        col1, col2 = st.columns(2)
        col1.metric("Total monthly (all flats)", f"{grand_monthly:.2f} €")
        col2.metric("Total annual  (all flats)", f"{grand_monthly * 12:.2f} €")

        st.divider()

        # ── Per-flat detail ────────────────────────────────────────
        st.subheader("Detail by flat")
        for (prop, flat), rows in grouped.items():
            label = f"{prop} — {flat}"
            with st.expander(label, expanded=False):
                table_rows = []
                active_monthly = _ZERO
                onetime_active = 0
                for r in rows:
                    active = _is_active(r[7], r[8], today)
                    mo = _monthly_equiv(r[5], r[6]) if active else _ZERO
                    if active:
                        if r[6] == "one-time":
                            onetime_active += 1
                        else:
                            active_monthly += mo
                    table_rows.append({
                        "ID":         r[0],
                        "Type":       r[4],
                        "Amount (€)": r[5],
                        "Frequency":  r[6],
                        "Monthly eq.": f"{_monthly_equiv(r[5], r[6]):.2f}" if r[6] != "one-time" else "—",
                        "Valid from":  r[7] or "—",
                        "Valid to":    r[8] if r[8] and r[8] != "None" else "open",
                        "Status":      "✓ Active" if active else "✗ Expired",
                    })

                df = pd.DataFrame(table_rows)
                st.dataframe(
                    df.style.apply(
                        lambda col: [
                            "color: #27ae60" if v == "✓ Active" else
                            "color: #8395a7"
                            for v in col
                        ] if col.name == "Status" else [""] * len(col),
                        axis=0,
                    ),
                    hide_index=True,
                )

                # Totals bar
                annual = active_monthly * 12
                note = f"  ·  +{onetime_active} one-time" if onetime_active else ""
                st.markdown(
                    f"<div style='display:flex;gap:32px;background:#1e2d3d;"
                    f"border-left:4px solid #3a7fc1;padding:8px 16px;"
                    f"border-radius:4px;margin-top:4px;'>"
                    f"<div><span style='color:#9ec5e8;font-size:0.8em;'>Monthly (active)</span>"
                    f"<br><b style='color:#fff;font-size:1.05em;'>{active_monthly:.2f} €</b></div>"
                    f"<div><span style='color:#9ec5e8;font-size:0.8em;'>Annual (active)</span>"
                    f"<br><b style='color:#fff;font-size:1.05em;'>{annual:.2f} €</b></div>"
                    f"<div style='align-self:center;color:#8395a7;font-size:0.85em;'>{note}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    st.divider()

    # ── Add / Edit / Delete ────────────────────────────────────────
    apartments = fetch("""
        SELECT a.id, a.name, a.flat, p.name
        FROM apartments a JOIN properties p ON a.property_id = p.id
        ORDER BY p.name, a.flat, a.name
    """)

    with st.expander("Add Cost"):
        if not apartments:
            st.warning("No apartments found.")
        else:
            apt_choice = st.selectbox(
                "Apartment", apartments,
                format_func=lambda x: f"{x[3]} — {x[2]} — {x[1]}" if x[2] else f"{x[3]} — {x[1]}",
                key="fc_apt_new",
            )
            col1, col2 = st.columns(2)
            with col1:
                type_opts     = ["Hausgeld", "Mortgage", "Grundsteuer",
                                 "Strom Vorauszahlung", "Internet", "Other"]
                cost_type_sel = st.selectbox("Cost type", type_opts, key="fc_type_sel")
                cost_type     = (st.text_input("Custom type", key="fc_custom_type")
                                 if cost_type_sel == "Other" else cost_type_sel)
                amount        = st.number_input("Amount (€)", min_value=0.0, key="fc_amount_new")
            with col2:
                frequency   = st.selectbox("Frequency", ["monthly", "annual", "one-time"],
                                           key="fc_freq_new")
                valid_from  = st.date_input("Valid from", key="fc_from_new")
                valid_to_en = st.checkbox("Set end date", key="fc_to_en_new")
                valid_to    = st.date_input("Valid to", key="fc_to_new") if valid_to_en else None

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
            type_opts    = ["Hausgeld", "Mortgage", "Grundsteuer",
                            "Strom Vorauszahlung", "Internet", "Other"]
            freq_opts    = ["monthly", "annual", "one-time"]
            cost_to_edit = st.selectbox(
                "Select cost", all_costs,
                format_func=lambda x: f"#{x[0]} — {x[1]} ({x[2]}) / {x[3]} ({x[5]})",
                key="cost_edit",
            )
            _, _, _, c_type, c_amt, c_freq, c_from, c_to = cost_to_edit
            col1, col2 = st.columns(2)
            with col1:
                edit_type_sel = st.selectbox(
                    "Cost type", type_opts,
                    index=type_opts.index(c_type) if c_type in type_opts else 5,
                    key=f"cedit_type_{cost_to_edit[0]}",
                )
                edit_type   = (st.text_input(
                    "Custom type",
                    value=c_type if c_type not in type_opts else "",
                    key=f"cedit_custom_{cost_to_edit[0]}",
                ) if edit_type_sel == "Other" else edit_type_sel)
                edit_amount = st.number_input(
                    "Amount (€)", value=float(c_amt), min_value=0.0,
                    key=f"cedit_amt_{cost_to_edit[0]}",
                )
            with col2:
                edit_freq  = st.selectbox(
                    "Frequency", freq_opts,
                    index=freq_opts.index(c_freq) if c_freq in freq_opts else 0,
                    key=f"cedit_freq_{cost_to_edit[0]}",
                )
                edit_from  = st.date_input(
                    "Valid from", value=date.fromisoformat(c_from),
                    key=f"cedit_from_{cost_to_edit[0]}",
                )
                edit_to_en = st.checkbox(
                    "Set end date", value=bool(c_to and c_to != "None"),
                    key=f"cedit_to_en_{cost_to_edit[0]}",
                )
                edit_to = (st.date_input(
                    "Valid to",
                    value=date.fromisoformat(c_to) if c_to and c_to != "None" else date.today(),
                    key=f"cedit_to_{cost_to_edit[0]}",
                ) if edit_to_en else None)

            if st.button("Save Cost", key="btn_save_cost"):
                execute(
                    "UPDATE flat_costs SET cost_type=?, amount=?, frequency=?, "
                    "valid_from=?, valid_to=? WHERE id=?",
                    (edit_type, edit_amount, edit_freq, str(edit_from),
                     str(edit_to) if edit_to else None, cost_to_edit[0]),
                )
                st.success("Cost updated.")
                st.rerun()

        with st.expander("Delete Cost"):
            to_del = st.selectbox(
                "Select cost", all_costs,
                format_func=lambda x: f"#{x[0]} — {x[1]} / {x[3]} ({x[5]})",
                key="cost_delete",
            )
            st.warning("This will permanently delete the cost entry.")
            if st.button("Delete Cost", type="primary", key="btn_del_cost"):
                execute("DELETE FROM flat_costs WHERE id=?", (to_del[0],))
                st.success("Cost deleted.")
                st.rerun()
