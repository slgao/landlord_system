import streamlit as st
import pandas as pd
from db import fetch, insert, execute


def show():
    st.header("Apartments")

    apt_data = fetch("""
        SELECT a.id, p.name, a.name, a.flat
        FROM apartments a
        JOIN properties p ON a.property_id = p.id
        ORDER BY p.name, a.flat, a.name
    """)

    if apt_data:
        df = pd.DataFrame(apt_data, columns=["ID", "Property", "Room / Apartment", "Flat"])
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No apartments found.")

    st.divider()

    properties = fetch("SELECT id, name FROM properties")

    with st.expander("Add Apartment"):
        if not properties:
            st.warning("Please create a property first.")
        else:
            prop_choice = st.selectbox("Property", properties,
                                       format_func=lambda x: x[1], key="apt_prop_new")
            apt_name = st.text_input(
                "Room / Apartment name", placeholder="e.g. Wohnung 1 - Zimmer A",
                help="WG: enter each room separately. Whole apartment: enter the unit name.",
                key="apt_name_new"
            )
            flat_name = st.text_input(
                "Flat / Wohnung", placeholder="e.g. Wohnung 1",
                help="All rooms sharing the same flat get the same label here. "
                     "Used to auto-count persons for Nebenkostenabrechnung.",
                key="apt_flat_new"
            )
            if st.button("Add Apartment", key="btn_add_apt"):
                insert("apartments", (prop_choice[0], apt_name, flat_name))
                st.success("Apartment added.")
                st.rerun()

    if apt_data:
        with st.expander("Edit Apartment"):
            apt_to_edit = st.selectbox(
                "Select apartment", apt_data,
                format_func=lambda x: f"#{x[0]} — {x[2]}  ({x[1]}, flat: {x[3] or '—'})",
                key="apt_edit"
            )
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Room / Apartment name", value=apt_to_edit[2],
                                         key=f"apt_name_{apt_to_edit[0]}")
            with col2:
                new_flat = st.text_input("Flat / Wohnung", value=apt_to_edit[3] or "",
                                         key=f"apt_flat_{apt_to_edit[0]}")
            if st.button("Save Apartment", key="btn_save_apt"):
                execute("UPDATE apartments SET name=?, flat=? WHERE id=?",
                        (new_name, new_flat, apt_to_edit[0]))
                st.success("Apartment updated.")
                st.rerun()

        with st.expander("Delete Apartment"):
            to_del = st.selectbox(
                "Select apartment", apt_data,
                format_func=lambda x: f"#{x[0]} — {x[2]} ({x[1]})",
                key="apt_delete"
            )
            st.warning("Deleting an apartment does not automatically remove linked contracts.")
            if st.button("Delete Apartment", type="primary", key="btn_del_apt"):
                execute("DELETE FROM apartments WHERE id=?", (to_del[0],))
                st.success(f"Apartment '{to_del[2]}' deleted.")
                st.rerun()
