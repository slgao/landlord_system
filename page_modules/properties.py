import streamlit as st
import pandas as pd
from db import fetch, insert, delete


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
        with st.expander("Delete Property"):
            to_del = st.selectbox("Select property", data,
                                  format_func=lambda x: f"#{x[0]} — {x[1]}",
                                  key="prop_delete")
            st.warning("Deleting a property does not automatically remove its apartments.")
            if st.button("Delete Property", type="primary", key="btn_del_prop"):
                delete("properties", to_del[0])
                st.success(f"Property '{to_del[1]}' deleted.")
                st.rerun()
