import streamlit as st
import pandas as pd
from db import fetch, insert, execute

_SCOPE_OPTS  = ["room", "shared"]
_SCOPE_LABEL = {"room": "Room only", "shared": "Shared (whole flat)"}


def _scope_radio(key, default="shared"):
    return st.radio(
        "Scope",
        _SCOPE_OPTS,
        index=_SCOPE_OPTS.index(default),
        format_func=lambda s: _SCOPE_LABEL[s],
        horizontal=True,
        key=key,
        help="**Room only** — meter belongs exclusively to this room (e.g. Heizkostenverteiler). "
             "**Shared (whole flat)** — meter is shared by all rooms in the WG flat.",
    )


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

        # ── Heizkostenverteiler ────────────────────────────────────────────────
        with st.expander("Heizkostenverteiler"):
            st.caption("Register heat cost allocators (Heizkostenverteiler) per apartment. "
                       "Readings are entered in the Nebenkostenabrechnung.")
            apt_heiz = st.selectbox(
                "Select apartment", apt_data,
                format_func=lambda x: f"#{x[0]} — {x[2]}  ({x[1]})",
                key="apt_heiz_sel"
            )
            meters = fetch(
                "SELECT id, serial_number, description, unit_label, "
                "COALESCE(conversion_factor, 1.0), COALESCE(scope, 'room') "
                "FROM heizung_meters WHERE apartment_id=? ORDER BY id",
                (apt_heiz[0],)
            )
            if meters:
                df_m = pd.DataFrame(
                    [(r[0], r[1], r[2], r[3], r[4], _SCOPE_LABEL[r[5]]) for r in meters],
                    columns=["ID", "Serial No.", "Description",
                             "Meter Unit", "Conv. Factor (→kWh)", "Scope"],
                )
                st.dataframe(df_m, hide_index=True)
            else:
                st.info("No meters registered for this apartment.")

            st.caption(
                "**How billing works:** meter reads in Einheiten → "
                "× conversion factor (per meter) = kWh → "
                "× price €/kWh (entered once per billing) = cost."
            )
            st.markdown("**Add meter**")
            col1, col2 = st.columns(2)
            with col1:
                m_serial = st.text_input("Serial number", key="m_serial",
                                         placeholder="e.g. ISTA-00123456")
                m_desc   = st.text_input("Description / Location", key="m_desc",
                                         placeholder="e.g. Wohnzimmer Heizkörper")
            with col2:
                m_unit   = st.text_input(
                    "Meter unit label", value="Einheiten", key="m_unit",
                    placeholder="e.g. Einheiten",
                    help="The unit shown on the physical meter display."
                )
                m_factor = st.number_input(
                    "Conversion factor (Einheiten → kWh)",
                    min_value=0.0, value=1.0, format="%.4f", key="m_factor",
                    help="From your ISTA bill: converts this meter's units to kWh. "
                         "Each Heizkörper can have a different factor. "
                         "Leave at 1.0 if the meter already reads in kWh."
                )
            m_scope = _scope_radio("m_scope_heiz", default="room")
            if st.button("Add Meter", key="btn_add_meter"):
                if not m_serial.strip():
                    st.warning("Serial number is required.")
                else:
                    execute(
                        "INSERT INTO heizung_meters "
                        "(apartment_id, serial_number, description, unit_label, conversion_factor, scope) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (apt_heiz[0], m_serial.strip(), m_desc.strip(),
                         m_unit.strip() or "Einheiten", m_factor, m_scope)
                    )
                    st.success("Meter added.")
                    st.rerun()

            if meters:
                st.markdown("**Delete meter**")
                to_del_m = st.selectbox(
                    "Select meter", meters,
                    format_func=lambda x: f"{x[1]} — {x[2]} [{_SCOPE_LABEL[x[5]]}]",
                    key="apt_meter_del"
                )
                if st.button("Delete Meter", key="btn_del_meter", type="primary"):
                    execute("DELETE FROM heizung_meters WHERE id=?", (to_del_m[0],))
                    st.success("Meter deleted.")
                    st.rerun()

        # ── Gaszähler ──────────────────────────────────────────────────────────
        with st.expander("Gaszähler"):
            st.caption("Register gas meters (Gaszähler) per apartment. "
                       "Z-Zahl and Brennwert are taken from the NBB gas bill; "
                       "the Umrechnungsfaktor (m³ → kWh) is computed automatically.")
            apt_gas = st.selectbox(
                "Select apartment", apt_data,
                format_func=lambda x: f"#{x[0]} — {x[2]}  ({x[1]})",
                key="apt_gas_sel"
            )
            gas_meters = fetch(
                "SELECT id, serial_number, description, z_zahl, brennwert, "
                "COALESCE(scope, 'shared') "
                "FROM gas_meters WHERE apartment_id=? ORDER BY id",
                (apt_gas[0],)
            )
            if gas_meters:
                gm_rows = [
                    {
                        "ID":               r[0],
                        "Serial No.":       r[1] or "—",
                        "Description":      r[2] or "—",
                        "Z-Zahl":           r[3],
                        "Brennwert":        r[4],
                        "Factor (m³→kWh)":  round(r[3] * r[4], 4),
                        "Scope":            _SCOPE_LABEL[r[5]],
                    }
                    for r in gas_meters
                ]
                st.dataframe(pd.DataFrame(gm_rows), hide_index=True)
            else:
                st.info("No gas meters registered for this apartment.")

            st.caption(
                "**How it works:** Verbrauch (m³) × Z-Zahl × Brennwert = kWh → "
                "× Arbeitspreis (€/kWh) = cost. "
                "Both values are printed on the NBB annual gas bill."
            )
            st.markdown("**Add gas meter**")
            col1, col2 = st.columns(2)
            with col1:
                gm_serial = st.text_input("Serial number (Zählernummer)", key="gm_serial",
                                          placeholder="e.g. 12345678")
                gm_desc   = st.text_input("Description / Location", key="gm_desc",
                                          placeholder="e.g. Keller")
            with col2:
                gm_z_zahl   = st.number_input("Z-Zahl (Zustandszahl)", min_value=0.0,
                                               value=1.0, format="%.4f", key="gm_z_zahl",
                                               help="Zustandszahl from the NBB gas bill.")
                gm_brennwert = st.number_input("Brennwert (kWh/m³)", min_value=0.0,
                                               value=10.0, format="%.4f", key="gm_brennwert",
                                               help="Brennwert from the NBB gas bill.")
            computed = gm_z_zahl * gm_brennwert
            st.caption(f"Computed Umrechnungsfaktor: **{computed:.4f} kWh/m³**")
            gm_scope = _scope_radio("m_scope_gas", default="shared")
            if st.button("Add Gas Meter", key="btn_add_gm"):
                execute(
                    "INSERT INTO gas_meters "
                    "(apartment_id, serial_number, description, z_zahl, brennwert, scope) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (apt_gas[0], gm_serial.strip() or None, gm_desc.strip() or None,
                     gm_z_zahl, gm_brennwert, gm_scope)
                )
                st.success("Gas meter added.")
                st.rerun()

            if gas_meters:
                st.markdown("**Delete gas meter**")
                to_del_gm = st.selectbox(
                    "Select gas meter", gas_meters,
                    format_func=lambda x: f"{x[1] or '—'} — {x[2] or '—'} "
                                          f"(Z={x[3]}, Bw={x[4]}) [{_SCOPE_LABEL[x[5]]}]",
                    key="apt_gm_del"
                )
                if st.button("Delete Gas Meter", key="btn_del_gm", type="primary"):
                    execute("DELETE FROM gas_meters WHERE id=?", (to_del_gm[0],))
                    st.success("Gas meter deleted.")
                    st.rerun()

        # ── Stromzähler ────────────────────────────────────────────────────────
        with st.expander("Stromzähler"):
            st.caption("Register electricity meters (Stromzähler) per apartment. "
                       "Usually one per apartment. The Zählernummer is shown when "
                       "entering the Strom Zählerstand in the Nebenkostenabrechnung.")
            apt_strom = st.selectbox(
                "Select apartment", apt_data,
                format_func=lambda x: f"#{x[0]} — {x[2]}  ({x[1]})",
                key="apt_strom_sel"
            )
            strom_meters = fetch(
                "SELECT id, serial_number, description, COALESCE(scope, 'shared') "
                "FROM strom_meters WHERE apartment_id=? ORDER BY id",
                (apt_strom[0],)
            )
            if strom_meters:
                df_sm = pd.DataFrame(
                    [(r[0], r[1], r[2], _SCOPE_LABEL[r[3]]) for r in strom_meters],
                    columns=["ID", "Serial No.", "Description", "Scope"],
                )
                st.dataframe(df_sm, hide_index=True)
            else:
                st.info("No Stromzähler registered for this apartment.")

            st.markdown("**Add Stromzähler**")
            col1, col2 = st.columns(2)
            with col1:
                sm_serial = st.text_input("Zählernummer", key="sm_serial",
                                          placeholder="e.g. 1ESY1160123456")
            with col2:
                sm_desc = st.text_input("Description / Location", key="sm_desc",
                                        placeholder="e.g. Keller, Hauptzähler")
            sm_scope = _scope_radio("m_scope_strom", default="shared")
            if st.button("Add Stromzähler", key="btn_add_sm"):
                if not sm_serial.strip():
                    st.warning("Zählernummer is required.")
                else:
                    if strom_meters:
                        st.warning(
                            "An electricity meter is already registered for this "
                            "apartment. Adding another one — make sure this is intended."
                        )
                    execute(
                        "INSERT INTO strom_meters "
                        "(apartment_id, serial_number, description, scope) "
                        "VALUES (?, ?, ?, ?)",
                        (apt_strom[0], sm_serial.strip(), sm_desc.strip() or None, sm_scope)
                    )
                    st.success("Stromzähler added.")
                    st.rerun()

            if strom_meters:
                st.markdown("**Delete Stromzähler**")
                to_del_sm = st.selectbox(
                    "Select meter", strom_meters,
                    format_func=lambda x: f"{x[1] or '—'} — {x[2] or '—'} [{_SCOPE_LABEL[x[3]]}]",
                    key="apt_sm_del"
                )
                if st.button("Delete Stromzähler", key="btn_del_sm", type="primary"):
                    execute("DELETE FROM strom_meters WHERE id=?", (to_del_sm[0],))
                    st.success("Stromzähler deleted.")
                    st.rerun()

        # ── Wasserzähler ───────────────────────────────────────────────────────
        with st.expander("Wasserzähler (Kalt-/Warmwasser)"):
            st.caption("Register water meters per apartment. "
                       "Typically one Kaltwasserzähler and one or more Warmwasserzähler. "
                       "Readings are entered in the Nebenkostenabrechnung.")
            apt_wm = st.selectbox(
                "Select apartment", apt_data,
                format_func=lambda x: f"#{x[0]} — {x[2]}  ({x[1]})",
                key="apt_wm_sel"
            )
            wasser_meters = fetch(
                "SELECT id, serial_number, description, type, COALESCE(scope, 'shared') "
                "FROM wasser_meters WHERE apartment_id=? ORDER BY type, id",
                (apt_wm[0],)
            )
            if wasser_meters:
                df_wm = pd.DataFrame([
                    (r[0], "Kaltwasser" if r[3] == "kalt" else "Warmwasser",
                     r[1] or "—", r[2] or "—", _SCOPE_LABEL[r[4]])
                    for r in wasser_meters
                ], columns=["ID", "Type", "Serial No.", "Description", "Scope"])
                st.dataframe(df_wm, hide_index=True)
            else:
                st.info("No Wasserzähler registered for this apartment.")

            st.markdown("**Add Wasserzähler**")
            col1, col2, col3 = st.columns([1, 1.5, 1.5])
            with col1:
                wm_type_label = st.radio(
                    "Type", ["Kaltwasser", "Warmwasser"], key="wm_type",
                )
            with col2:
                wm_serial = st.text_input("Zählernummer", key="wm_serial",
                                          placeholder="e.g. 22A1234567")
            with col3:
                wm_desc = st.text_input("Description / Location", key="wm_desc",
                                        placeholder="e.g. Bad, Küche")
            wm_scope = _scope_radio("m_scope_wasser", default="shared")
            if st.button("Add Wasserzähler", key="btn_add_wm"):
                if not wm_serial.strip():
                    st.warning("Zählernummer is required.")
                else:
                    wm_type = "kalt" if wm_type_label == "Kaltwasser" else "warm"
                    if wm_type == "kalt":
                        existing_kalt = [m for m in wasser_meters if m[3] == "kalt"]
                        if existing_kalt:
                            st.warning(
                                "A Kaltwasserzähler is already registered for this "
                                "apartment. Adding another one — make sure this is intended."
                            )
                    execute(
                        "INSERT INTO wasser_meters "
                        "(apartment_id, serial_number, description, type, scope) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (apt_wm[0], wm_serial.strip(), wm_desc.strip() or None,
                         wm_type, wm_scope)
                    )
                    st.success(f"{wm_type_label} added.")
                    st.rerun()

            if wasser_meters:
                st.markdown("**Delete Wasserzähler**")
                to_del_wm = st.selectbox(
                    "Select meter", wasser_meters,
                    format_func=lambda x: f"[{('Kalt' if x[3]=='kalt' else 'Warm')}] "
                                          f"{x[1] or '—'} — {x[2] or '—'} [{_SCOPE_LABEL[x[4]]}]",
                    key="apt_wm_del"
                )
                if st.button("Delete Wasserzähler", key="btn_del_wm", type="primary"):
                    execute("DELETE FROM wasser_meters WHERE id=?", (to_del_wm[0],))
                    st.success("Wasserzähler deleted.")
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
