import streamlit as st
import pandas as pd
from db import fetch, insert, delete, execute, get_config, set_config


def show():
    st.header("Properties")

    data = fetch("SELECT id, name, address FROM properties")

    if data:
        df = pd.DataFrame(data, columns=["ID", "Property Name", "Address"])
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No properties yet.")

    st.divider()

    with st.expander("Add Property"):
        name    = st.text_input("Property name", key="prop_name_new")
        address = st.text_input("Address",        key="prop_address_new")
        if st.button("Add Property", key="btn_add_prop"):
            insert("properties", (name, address))
            st.success("Property added.")
            st.rerun()

    if data:
        with st.expander("Edit Property"):
            to_edit = st.selectbox("Select property", data,
                                   format_func=lambda x: f"#{x[0]} — {x[1]}",
                                   key="prop_edit_sel")
            if st.session_state.get("_prop_edit_id") != to_edit[0]:
                st.session_state["_prop_edit_id"]   = to_edit[0]
                st.session_state["prop_edit_name"]  = to_edit[1]
                st.session_state["prop_edit_addr"]  = to_edit[2]
            new_name    = st.text_input("Property name", key="prop_edit_name")
            new_address = st.text_input("Address",        key="prop_edit_addr")
            if st.button("Save Changes", key="btn_edit_prop"):
                execute("UPDATE properties SET name=?, address=? WHERE id=?",
                        (new_name, new_address, to_edit[0]))
                st.success("Property updated.")
                st.rerun()

    with st.expander("Landlord & Billing Info", expanded=not get_config("landlord_name")):
        st.caption("Saved globally and optionally printed on billing PDFs (Nebenkostenabrechnung).")
        col1, col2 = st.columns(2)
        with col1:
            ll_name    = st.text_input("Landlord name",
                                       value=get_config("landlord_name", ""),
                                       key="ll_name")
            ll_address = st.text_input("Landlord address",
                                       value=get_config("landlord_address", ""),
                                       key="ll_address")
        with col2:
            ll_iban    = st.text_input("IBAN",
                                       value=get_config("landlord_iban", ""),
                                       key="ll_iban")
            ll_bank    = st.text_input("Bank name",
                                       value=get_config("landlord_bank", ""),
                                       key="ll_bank")
        if st.button("Save Landlord Info", key="btn_save_ll"):
            set_config("landlord_name",    ll_name)
            set_config("landlord_address", ll_address)
            set_config("landlord_iban",    ll_iban)
            set_config("landlord_bank",    ll_bank)
            st.success("Landlord info saved.")
            st.rerun()

    if data:
        with st.expander("Delete Property"):
            to_del = st.selectbox("Select property", data,
                                  format_func=lambda x: f"#{x[0]} — {x[1]}",
                                  key="prop_delete")
            st.warning("Deleting a property does not automatically remove its apartments.")
            if st.button("Delete Property", type="primary", key="btn_del_prop"):
                delete("properties", to_del[0])
                st.success(f"Property '{to_del[1]}' deleted.")
                st.rerun()
