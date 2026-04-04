import streamlit as st
import pandas as pd
from db import fetch, insert, execute


def show():
    st.header("Tenants")

    data = fetch("""
        SELECT t.id, t.name, t.email, t.gender, a.name
        FROM tenants t
        LEFT JOIN contracts c ON t.id = c.tenant_id
        LEFT JOIN apartments a ON c.apartment_id = a.id
    """)

    if data:
        df = pd.DataFrame(data, columns=["ID", "Tenant", "Email", "Gender", "Apartment"])
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No tenants yet.")

    st.divider()

    with st.expander("Add Tenant"):
        name   = st.text_input("Name",  key="new_t_name")
        email  = st.text_input("Email", key="new_t_email")
        gender = st.selectbox("Gender", ["male", "female", "diverse"], key="new_t_gender")
        if st.button("Add Tenant", key="btn_add_tenant"):
            insert("tenants", (name, email, gender))
            st.success("Tenant added.")
            st.rerun()

    if data:
        with st.expander("Edit Tenant"):
            tenant_opts = [(r[0], r[1], r[2], r[3]) for r in data]
            t = st.selectbox("Select tenant", tenant_opts,
                             format_func=lambda x: x[1], key="tenant_edit")
            col1, col2 = st.columns(2)
            with col1:
                new_name  = st.text_input("Name",  value=t[1], key=f"t_name_{t[0]}")
                new_email = st.text_input("Email", value=t[2] or "", key=f"t_email_{t[0]}")
            with col2:
                gender_opts = ["male", "female", "diverse"]
                cur_gender  = t[3] if t[3] in gender_opts else "diverse"
                new_gender  = st.selectbox("Gender", gender_opts,
                                           index=gender_opts.index(cur_gender),
                                           key=f"t_gender_{t[0]}")

            all_apts   = fetch("SELECT id, name FROM apartments")
            cur_apt    = fetch("SELECT apartment_id FROM contracts WHERE tenant_id=? LIMIT 1", (t[0],))
            cur_apt_id = cur_apt[0][0] if cur_apt else None
            apt_ids    = [a[0] for a in all_apts]
            apt_idx    = apt_ids.index(cur_apt_id) if cur_apt_id in apt_ids else 0
            new_apt    = None
            if all_apts:
                new_apt = st.selectbox("Apartment (via contract)", all_apts,
                                       format_func=lambda x: x[1],
                                       index=apt_idx, key=f"t_apt_{t[0]}")

            if st.button("Save Changes", key="btn_save_tenant"):
                execute("UPDATE tenants SET name=?, email=?, gender=? WHERE id=?",
                        (new_name, new_email, new_gender, t[0]))
                if new_apt and cur_apt_id:
                    execute("UPDATE contracts SET apartment_id=? WHERE tenant_id=?",
                            (new_apt[0], t[0]))
                st.success(f"Tenant '{new_name}' updated.")
                st.rerun()

        with st.expander("Delete Tenant"):
            to_del = st.selectbox("Select tenant", data,
                                  format_func=lambda x: f"#{x[0]} — {x[1]}",
                                  key="tenant_delete")
            st.warning("This will permanently remove the tenant.")
            if st.button("Delete Tenant", type="primary", key="btn_del_tenant"):
                execute("DELETE FROM tenants WHERE id=?", (to_del[0],))
                st.success(f"Tenant '{to_del[1]}' removed.")
                st.rerun()
