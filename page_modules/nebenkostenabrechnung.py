import json
import streamlit as st
import calendar
from datetime import date, timedelta
from pathlib import Path
from db import fetch, execute, get_config, get_tenant_gender
from logic import (strom_calc_detail, gas_calc_detail, water_calc_detail,
                   betriebskosten_calc, heizung_calc_detail, warmwasser_calc_detail)
from pdfgen import invoice_pdf


# ── Profile helpers ────────────────────────────────────────────────────────────

def _load_profile_into_state(data: dict):
    st.session_state["nk_num_tenants"] = data.get("num_tenants", 1)

    for util in ("strom", "gas", "water"):
        if data.get(util):
            d = data[util]
            bill_s = date.fromisoformat(d["bill_start"])
            bill_e = date.fromisoformat(d["bill_end"])
            eff_s  = date.fromisoformat(d["eff_start"])
            eff_e  = date.fromisoformat(d["eff_end"])
            st.session_state[f"include_{util}"]       = True
            st.session_state[f"{util}_start"]         = bill_s
            st.session_state[f"{util}_end"]           = bill_e
            st.session_state[f"{util}_eff_start"]     = eff_s
            st.session_state[f"{util}_eff_end"]       = eff_e
            st.session_state[f"{util}_limit"]         = float(d.get("prepay_pm", 0))
            st.session_state[f"_{util}_bill_key"]     = (bill_s, bill_e)
            if util == "strom":
                st.session_state["strom_start_kwh"]     = float(d.get("start_kwh", 0))
                st.session_state["strom_end_kwh"]       = float(d.get("end_kwh", 0))
                st.session_state["strom_arbeitspreis"]  = float(d.get("arbeitspreis", 0))
                st.session_state["strom_grundpreis"]    = float(d.get("grundpreis_monthly", 0))
                st.session_state["strom_is_pauschale"]  = bool(d.get("is_pauschale", False))
            elif util == "gas":
                st.session_state["gas_start_m3"]        = float(d.get("start_m3", 0))
                st.session_state["gas_end_m3"]          = float(d.get("end_m3", 0))
                st.session_state["gas_umrechnung"]      = float(d.get("umrechnungsfaktor", 10.0))
                st.session_state["gas_arbeitspreis"]    = float(d.get("arbeitspreis", 0))
                st.session_state["gas_grundpreis"]      = float(d.get("grundpreis_monthly", 0))
                st.session_state["gas_is_pauschale"]    = bool(d.get("is_pauschale", False))
            elif util == "water":
                st.session_state["water_start_m3"]      = float(d.get("start_m3", 0))
                st.session_state["water_end_m3"]        = float(d.get("end_m3", 0))
                st.session_state["water_frischwasser"]  = float(d.get("frischwasser_per_m3", 0))
                st.session_state["water_abwasser"]      = float(d.get("abwasser_per_m3", 0))
                st.session_state["water_is_pauschale"]  = bool(d.get("is_pauschale", False))
        else:
            st.session_state[f"include_{util}"] = False

    if data.get("warmwater"):
        d = data["warmwater"]
        bill_s = date.fromisoformat(d["bill_start"])
        bill_e = date.fromisoformat(d["bill_end"])
        eff_s  = date.fromisoformat(d["eff_start"])
        eff_e  = date.fromisoformat(d["eff_end"])
        st.session_state["include_warmwater"] = True
        st.session_state["ww_start"]          = bill_s
        st.session_state["ww_end"]            = bill_e
        st.session_state["ww_eff_start"]      = eff_s
        st.session_state["ww_eff_end"]        = eff_e
        st.session_state["ww_limit"]          = float(d.get("prepay_pm", 0))
        st.session_state["ww_frischwasser"]   = float(d.get("frischwasser_per_m3", 0))
        st.session_state["ww_abwasser"]       = float(d.get("abwasser_per_m3", 0))
        st.session_state["ww_heizenergie"]    = float(d.get("heizenergie_per_m3", 0))
        st.session_state["ww_is_pauschale"]   = bool(d.get("is_pauschale", False))
        st.session_state["_ww_bill_key"]      = (bill_s, bill_e)
        for m in d.get("meters", []):
            mid = m["meter_id"]
            st.session_state[f"ww_start_{mid}"] = float(m.get("start", 0))
            st.session_state[f"ww_end_{mid}"]   = float(m.get("end", 0))
    else:
        st.session_state["include_warmwater"] = False

    if data.get("bk"):
        d = data["bk"]
        st.session_state["include_bk"]      = True
        st.session_state["bk_s_month"]      = d["bill_s_month"]
        st.session_state["bk_s_year"]       = d["bill_s_year"]
        st.session_state["bk_e_month"]      = d["bill_e_month"]
        st.session_state["bk_e_year"]       = d["bill_e_year"]
        st.session_state["bk_eff_s_month"]  = d["eff_s_month"]
        st.session_state["bk_eff_s_year"]   = d["eff_s_year"]
        st.session_state["bk_eff_e_month"]  = d["eff_e_month"]
        st.session_state["bk_eff_e_year"]   = d["eff_e_year"]
        st.session_state["bk_limit"]        = float(d.get("prepay_pm", 0))
        st.session_state["bk_cost"]         = float(d.get("total_cost", 0))
        st.session_state["_bk_bill_key"]    = (
            d["bill_s_month"], d["bill_s_year"],
            d["bill_e_month"], d["bill_e_year"],
        )
    else:
        st.session_state["include_bk"] = False

    # Extra items
    _reset_extra_items(data.get("extra_items", []))
    st.session_state["include_extra"] = bool(data.get("extra_items"))

    # Heizkosten
    if data.get("heizung"):
        h = data["heizung"]
        bill_s = date.fromisoformat(h["bill_start"])
        bill_e = date.fromisoformat(h["bill_end"])
        eff_s  = date.fromisoformat(h["eff_start"])
        eff_e  = date.fromisoformat(h["eff_end"])
        st.session_state["include_heiz"]      = True
        st.session_state["heiz_start"]        = bill_s
        st.session_state["heiz_end"]          = bill_e
        st.session_state["heiz_eff_start"]    = eff_s
        st.session_state["heiz_eff_end"]      = eff_e
        st.session_state["heiz_limit"]        = float(h.get("prepay_pm", 0))
        st.session_state["heiz_price_kwh"]    = float(h.get("price_kwh", 0))
        st.session_state["heiz_is_pauschale"] = bool(h.get("is_pauschale", False))
        st.session_state["_heiz_bill_key"]    = (bill_s, bill_e)
        for m in h.get("meters", []):
            mid = m["meter_id"]
            st.session_state[f"heiz_start_{mid}"]  = float(m.get("start", 0))
            st.session_state[f"heiz_end_{mid}"]    = float(m.get("end", 0))
            st.session_state[f"heiz_factor_{mid}"] = float(m.get("conversion_factor", 1.0))
    else:
        st.session_state["include_heiz"] = False


def _reset_extra_items(items: list):
    """Replace session-state extra items with the given list."""
    for iid in st.session_state.get("extra_item_ids", []):
        st.session_state.pop(f"extra_desc_{iid}", None)
        st.session_state.pop(f"extra_amt_{iid}", None)
    st.session_state["extra_item_ids"]     = []
    st.session_state["extra_item_counter"] = 0
    for item in items:
        iid = st.session_state["extra_item_counter"]
        st.session_state["extra_item_ids"].append(iid)
        st.session_state[f"extra_desc_{iid}"] = item.get("description", "")
        st.session_state[f"extra_amt_{iid}"]  = float(item.get("amount", 0.0))
        st.session_state["extra_item_counter"] += 1


def _collect_extra_items() -> list:
    """Read current extra-item widget values from session state."""
    items = []
    for iid in st.session_state.get("extra_item_ids", []):
        desc = st.session_state.get(f"extra_desc_{iid}", "").strip()
        amt  = float(st.session_state.get(f"extra_amt_{iid}", 0.0))
        if desc:
            items.append({"description": desc, "amount": amt})
    return items


# ── Page ───────────────────────────────────────────────────────────────────────

def show():
    st.header("Nebenkostenabrechnung")

    # ── Landlord & Signature ───────────────────────────────────────
    landlord_name = st.text_input(
        "Landlord name",
        value=get_config("landlord_name", "Ihr Vermieter"),
        key="nk_landlord_name",
    )
    sig_path = "pdf/signature.png"
    if Path(sig_path).exists():
        st.image(sig_path, width=200, caption="Current signature")
    sig_upload = st.file_uploader("Upload signature image (PNG/JPG)",
                                  type=["png", "jpg", "jpeg"], key="sig_abrechnung")
    if sig_upload:
        Path("pdf").mkdir(exist_ok=True)
        with open(sig_path, "wb") as f:
            f.write(sig_upload.read())
        st.success("Signature saved.")

    # ── Tenant selection ───────────────────────────────────────────
    contract_tenants = fetch("""
        SELECT DISTINCT t.id, t.name FROM tenants t
        JOIN contracts c ON c.tenant_id = t.id
    """)
    if not contract_tenants:
        st.warning("No tenants with contracts found.")
        return

    tenant_choice = st.selectbox("Tenant", contract_tenants, format_func=lambda x: x[1])
    tenant = tenant_choice[1]
    gender = get_tenant_gender(tenant)

    # ── Load Billing Profile ───────────────────────────────────────
    profiles = fetch(
        "SELECT id, label, created_date FROM billing_profiles "
        "WHERE tenant_id=? ORDER BY created_date DESC",
        (tenant_choice[0],)
    )
    if profiles:
        with st.expander("Load Billing Profile"):
            sel_prof = st.selectbox(
                "Select profile", profiles,
                format_func=lambda x: f"{x[1]}  ({x[2]})",
                key="sel_profile",
            )
            col_load, col_del = st.columns(2)
            with col_load:
                if st.button("Load", key="btn_load_profile"):
                    row = fetch("SELECT data FROM billing_profiles WHERE id=?", (sel_prof[0],))
                    if row:
                        data = json.loads(row[0][0])
                        _load_profile_into_state(data)
                        # Pre-select the contract saved with this profile
                        if "contract_id" in data:
                            st.session_state["_nk_preselect_contract_id"] = data["contract_id"]
                            # Suppress the tenant/contract-change reset so profile
                            # values (num_tenants, extra items, etc.) are not overwritten
                            st.session_state["_nk_tenant_id"] = (
                                tenant_choice[0], data["contract_id"]
                            )
                        st.success(f"Profile '{sel_prof[1]}' loaded.")
                        st.rerun()
            with col_del:
                if st.button("Delete profile", key="btn_del_profile"):
                    execute("DELETE FROM billing_profiles WHERE id=?", (sel_prof[0],))
                    st.success(f"Profile '{sel_prof[1]}' deleted.")
                    st.rerun()

    # ── Contract / Apartment selector ─────────────────────────────
    all_contracts = fetch("""
        SELECT c.id, c.start_date, c.end_date, a.name, a.id
        FROM contracts c
        JOIN apartments a ON c.apartment_id = a.id
        WHERE c.tenant_id=? ORDER BY c.start_date DESC
    """, (tenant_choice[0],))
    if not all_contracts:
        st.warning("No contract found for this tenant.")
        return

    def _fmt_contract(row):
        cid, s, e, apt, _ = row
        e_str = e if e and e != "None" else "unbefristet"
        return f"{apt}  ({s} – {e_str})"

    # Apply contract pre-selection from a loaded billing profile
    _preselect_cid = st.session_state.pop("_nk_preselect_contract_id", None)
    if _preselect_cid:
        for _c in all_contracts:
            if _c[0] == _preselect_cid:
                st.session_state["nk_contract_sel"] = _c
                break

    if len(all_contracts) > 1:
        contract_row = st.selectbox(
            "Contract / Apartment", all_contracts,
            format_func=_fmt_contract,
            key="nk_contract_sel",
        )
    else:
        contract_row = all_contracts[0]

    selected_contract_id  = contract_row[0]
    selected_apartment_id = contract_row[4]

    # For WG flats: collect all apartment IDs that share the same flat label
    # so meters registered on any sibling room are visible here too.
    _flat_apt_rows = fetch("""
        SELECT a2.id FROM apartments a2
        WHERE a2.property_id = (SELECT property_id FROM apartments WHERE id = ?)
          AND a2.flat IS NOT NULL AND a2.flat != ''
          AND a2.flat = (SELECT flat FROM apartments WHERE id = ?)
    """, (selected_apartment_id, selected_apartment_id))
    _flat_apt_ids = [r[0] for r in _flat_apt_rows] if _flat_apt_rows else []
    if selected_apartment_id not in _flat_apt_ids:
        _flat_apt_ids.append(selected_apartment_id)
    _apt_in  = ",".join(str(i) for i in _flat_apt_ids)
    _own_id  = selected_apartment_id

    def _meter_where(extra=""):
        """Scope-aware WHERE clause: room-scoped meters only for own apt,
        shared meters from any apt in the same flat."""
        return (
            f"((COALESCE(scope,'room') = 'room' AND apartment_id = {_own_id}) "
            f" OR (scope = 'shared' AND apartment_id IN ({_apt_in}))) "
            f"{extra}"
        )

    c_start_str, c_end_str = contract_row[1], contract_row[2]
    contract_start = date.fromisoformat(c_start_str)
    contract_end   = (date.fromisoformat(c_end_str)
                      if c_end_str and c_end_str != "None" else None)
    end_display = contract_end.strftime("%d.%m.%Y") if contract_end else "unbefristet"

    addr_row = fetch("""
        SELECT p.address FROM apartments a
        JOIN properties p ON p.id = a.property_id
        WHERE a.id = ?
    """, (selected_apartment_id,))
    address = addr_row[0][0] if addr_row and addr_row[0][0] else ""

    # ── Co-tenants for this contract ───────────────────────────────
    co_tenants_rows = fetch(
        "SELECT name, gender, in_contract FROM co_tenants WHERE contract_id=? ORDER BY id",
        (selected_contract_id,)
    )
    # All co-tenants (for person count and info display)
    all_co_tenants = [{"name": r[0], "gender": r[1], "in_contract": bool(r[2])}
                      for r in co_tenants_rows]
    # Only those named on the contract go into the PDF
    co_tenants = [c for c in all_co_tenants if c["in_contract"]]

    info_lines = (
        f"**Contract:** {contract_row[3]}  ·  "
        f"{contract_start.strftime('%d.%m.%Y')} — {end_display}"
    )
    if co_tenants:
        info_lines += "  \n**Mitmieter (in contract → appear in PDF):** " + \
                      ", ".join(c["name"] for c in co_tenants)
    other_occupants = [c for c in all_co_tenants if not c["in_contract"]]
    if other_occupants:
        info_lines += "  \n**Other occupants (not in PDF):** " + \
                      ", ".join(c["name"] for c in other_occupants)
    info_lines += "  \n" + (f"**Address:** {address}" if address else "No address found for this property.")
    st.info(info_lines)

    # ── Auto-count persons in flat ─────────────────────────────────
    # Primary tenant + all co-tenants (regardless of contract status)
    co_tenant_count = len(all_co_tenants)
    if co_tenant_count > 0:
        auto_count = 1 + co_tenant_count
    else:
        persons_in_flat = fetch("""
            SELECT COUNT(DISTINCT c.tenant_id)
            FROM contracts c
            JOIN apartments a ON c.apartment_id = a.id
            WHERE COALESCE(c.terminated, 0) = 0
            AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= date('now'))
            AND a.flat IS NOT NULL AND a.flat != ''
            AND a.property_id = (SELECT property_id FROM apartments WHERE id=?)
            AND a.flat = (SELECT flat FROM apartments WHERE id=?)
        """, (selected_apartment_id, selected_apartment_id))
        auto_count = persons_in_flat[0][0] if persons_in_flat and persons_in_flat[0][0] else 1

    # Reset when tenant OR contract changes
    _nk_key = (tenant_choice[0], selected_contract_id)
    if st.session_state.get("_nk_tenant_id") != _nk_key:
        st.session_state["_nk_tenant_id"]  = _nk_key
        st.session_state["nk_num_tenants"] = int(auto_count)
        _reset_extra_items([])

    # Ensure extra-item state is initialised even without a tenant switch
    if "extra_item_ids" not in st.session_state:
        st.session_state["extra_item_ids"]     = []
        st.session_state["extra_item_counter"] = 0

    st.divider()
    num_tenants = st.number_input("Tenants in flat", min_value=1, key="nk_num_tenants")
    if auto_count > 1:
        if co_tenant_count > 0:
            in_contract_count = len(co_tenants)
            st.caption(
                f"Auto-detected {auto_count} persons (primary tenant + {co_tenant_count} co-tenant(s); "
                f"{in_contract_count} named in contract → appear in PDF)."
            )
        else:
            st.caption(f"Auto-detected {auto_count} active tenants sharing the same flat.")

    def _effective(bill_start, bill_end):
        c_end = contract_end if contract_end else bill_end
        eff_s = max(bill_start, contract_start)
        eff_e = min(bill_end, c_end)
        return (eff_s, eff_e) if eff_s <= eff_e else None

    # ── Cost type selection ────────────────────────────────────────
    st.divider()
    st.subheader("Select Cost Types to Include")
    include_strom     = st.checkbox("Strom (Electricity)",                           key="include_strom")
    include_gas       = st.checkbox("Gas",                                            key="include_gas")
    include_water     = st.checkbox("Kaltwasser (Cold Water)",                        key="include_water")
    include_warmwater = st.checkbox("Warmwasser (Hot Water)",                         key="include_warmwater")
    include_heiz      = st.checkbox("Heizkosten (Heizkostenverteiler)",              key="include_heiz")
    include_bk        = st.checkbox("Betriebskosten (Operating costs)",               key="include_bk")
    include_extra     = st.checkbox("Zusätzliche Positionen (damages, agreements…)", key="include_extra")

    strom_data = gas_data = water_data = warmwater_data = heiz_data = bk_data = extra_data = None
    meter_inputs = []
    warm_meter_inputs = []

    # ── Strom ──────────────────────────────────────────────────────
    if include_strom:
        st.subheader("Strom")

        _apt_strom_meters = fetch(
            f"SELECT id, serial_number, description "
            f"FROM strom_meters WHERE {_meter_where()} ORDER BY id",
        )
        strom_meter_info = None
        if _apt_strom_meters:
            if len(_apt_strom_meters) == 1:
                sm = _apt_strom_meters[0]
            else:
                sm = st.selectbox(
                    "Stromzähler",
                    _apt_strom_meters,
                    format_func=lambda x: f"{x[1] or '—'} ({x[2] or '—'})",
                    key="strom_meter_sel",
                )
            strom_meter_info = {
                "meter_id":    sm[0],
                "serial":      sm[1] or "",
                "description": sm[2] or "",
            }
            st.info(
                f"Stromzähler registriert: **{sm[1] or '—'}**  ·  "
                f"{sm[2] or '—'}"
            )
        else:
            st.caption(
                "ℹ️ No Stromzähler registered for this apartment — register one in "
                "the Apartments page to attach the Zählernummer to this billing."
            )

        col1, col2 = st.columns(2)
        with col1:
            strom_bill_start = st.date_input("Billing period start",
                                             value=date.today().replace(month=1, day=1),
                                             min_value=date.today() - timedelta(days=365 * 20),
                                             key="strom_start")
        with col2:
            strom_bill_end = st.date_input("Billing period end",
                                           value=date.today().replace(month=12, day=31),
                                           key="strom_end")

        strom_eff = _effective(strom_bill_start, strom_bill_end)
        if strom_eff is None:
            st.warning("Tenant's contract does not overlap with the Strom billing period.")
        else:
            s_auto_s, s_auto_e = strom_eff
            _sk = (strom_bill_start, strom_bill_end)
            if st.session_state.get("_strom_bill_key") != _sk:
                st.session_state["strom_eff_start"] = s_auto_s
                st.session_state["strom_eff_end"]   = s_auto_e
                st.session_state["_strom_bill_key"] = _sk
            st.caption("Tenant's effective period (auto-detected, editable):")
            col1, col2 = st.columns(2)
            with col1:
                s_eff_start = st.date_input("Effective start",
                                            min_value=date.today() - timedelta(days=365 * 20),
                                            key="strom_eff_start")
            with col2:
                s_eff_end = st.date_input("Effective end", key="strom_eff_end")
            s_eff_days = max(1, (s_eff_end - s_eff_start).days + 1)
            st.caption(f"{s_eff_days} days")

            st.caption("Meter readings & tariff:")
            col1, col2 = st.columns(2)
            with col1:
                strom_start_kwh = st.number_input("Anfang Zählerstand (kWh)",
                                                  min_value=0.0, format="%.2f",
                                                  key="strom_start_kwh")
                strom_arbeitspreis = st.number_input("Arbeitspreis (€/kWh)",
                                                     min_value=0.0, format="%.3f",
                                                     key="strom_arbeitspreis")
            with col2:
                strom_end_kwh = st.number_input("Ende Zählerstand (kWh)",
                                                min_value=0.0, format="%.2f",
                                                key="strom_end_kwh")
                strom_grundpreis = st.number_input("Grundpreis (€/Monat)",
                                                   min_value=0.0, format="%.2f",
                                                   key="strom_grundpreis")
            strom_limit_pm = st.number_input("Prepayment per month (€)", min_value=0.0,
                                             key="strom_limit")
            strom_is_pauschale = st.checkbox(
                "Pauschale — prepayment is a hard limit (no refund if unused, "
                "Nachzahlung if exceeded)",
                key="strom_is_pauschale",
            )

            strom_bill_days = max(1, (strom_bill_end - strom_bill_start).days + 1)
            calc = strom_calc_detail(
                strom_start_kwh, strom_end_kwh, strom_arbeitspreis, strom_grundpreis,
                num_tenants, strom_bill_days, s_eff_days, strom_limit_pm,
                is_pauschale=strom_is_pauschale,
            )
            st.info(
                f"Verbrauch: **{calc['verbrauch']:.2f} kWh**  ·  "
                f"Ihr Anteil: **{calc['cost_tenant']:.2f} €**  ·  "
                f"Vorauszahlung: **{calc['prepay']:.2f} €**  ·  "
                f"Nachzahlung: **{calc['nach']:.2f} €**"
            )
            strom_data = {
                "bill_period":         f"{strom_bill_start.strftime('%d.%m.%Y')} – {strom_bill_end.strftime('%d.%m.%Y')}",
                "bill_days":           strom_bill_days,
                "period":              f"{s_eff_start.strftime('%d.%m.%Y')} – {s_eff_end.strftime('%d.%m.%Y')}",
                "days":                s_eff_days,
                "num_tenants":         int(num_tenants),
                "monthly_limit":       strom_limit_pm,
                "start_kwh":           strom_start_kwh,
                "end_kwh":             strom_end_kwh,
                "arbeitspreis":        strom_arbeitspreis,
                "grundpreis_monthly":  strom_grundpreis,
                **calc,
                "cost":        calc["cost_tenant"],
                "limit":       calc["prepay"],
                "is_pauschale": bool(strom_is_pauschale),
                "meter_serial":      strom_meter_info["serial"]      if strom_meter_info else "",
                "meter_description": strom_meter_info["description"] if strom_meter_info else "",
            }

    # ── Gas ────────────────────────────────────────────────────────
    if include_gas:
        st.subheader("Gas")

        # Auto-fill Umrechnungsfaktor from registered Gaszähler for this apartment
        _apt_gas_meters = fetch(
            f"SELECT id, serial_number, description, z_zahl, brennwert "
            f"FROM gas_meters WHERE {_meter_where()} ORDER BY id",
        )
        _gm_factor_default = 10.0
        if _apt_gas_meters:
            _gm = _apt_gas_meters[0]
            _gm_factor_default = round(_gm[3] * _gm[4], 4)
            # Always sync session state to the registered meter value so the
            # number_input below shows the correct factor on every render.
            # The registered meter is the source of truth; the user can edit
            # the field for one-off overrides within the current rerun.
            st.session_state["gas_umrechnung"] = _gm_factor_default
            meter_label = _gm[1] or "—"
            st.info(
                f"Gaszähler registriert: **{meter_label}** ({_gm[2] or '—'})  ·  "
                f"Z-Zahl: **{_gm[3]}**  ·  Brennwert: **{_gm[4]}**  ·  "
                f"Umrechnungsfaktor: **{_gm_factor_default:.4f} kWh/m³**"
            )

        col1, col2 = st.columns(2)
        with col1:
            gas_bill_start = st.date_input("Billing period start",
                                           value=date.today().replace(month=1, day=1),
                                           min_value=date.today() - timedelta(days=365 * 20),
                                           key="gas_start")
        with col2:
            gas_bill_end = st.date_input("Billing period end",
                                         value=date.today().replace(month=12, day=31),
                                         key="gas_end")

        gas_eff = _effective(gas_bill_start, gas_bill_end)
        if gas_eff is None:
            st.warning("Tenant's contract does not overlap with the Gas billing period.")
        else:
            g_auto_s, g_auto_e = gas_eff
            _gk = (gas_bill_start, gas_bill_end)
            if st.session_state.get("_gas_bill_key") != _gk:
                st.session_state["gas_eff_start"] = g_auto_s
                st.session_state["gas_eff_end"]   = g_auto_e
                st.session_state["_gas_bill_key"] = _gk
            st.caption("Tenant's effective period (auto-detected, editable):")
            col1, col2 = st.columns(2)
            with col1:
                g_eff_start = st.date_input("Effective start",
                                            min_value=date.today() - timedelta(days=365 * 20),
                                            key="gas_eff_start")
            with col2:
                g_eff_end = st.date_input("Effective end", key="gas_eff_end")
            g_eff_days = max(1, (g_eff_end - g_eff_start).days + 1)
            st.caption(f"{g_eff_days} days")

            st.caption("Meter readings & tariff:")
            col1, col2 = st.columns(2)
            with col1:
                gas_start_m3 = st.number_input("Anfang Zählerstand (m³)",
                                               min_value=0.0, format="%.3f",
                                               key="gas_start_m3")
                gas_umrechnung = st.number_input("Umrechnungsfaktor (kWh/m³)",
                                                 min_value=0.0, value=_gm_factor_default,
                                                 format="%.4f",
                                                 key="gas_umrechnung",
                                                 help="Z-Zahl × Brennwert — auto-filled from registered "
                                                      "Gaszähler, or enter manually from your NBB gas bill")
                gas_grundpreis = st.number_input("Grundpreis (€/Monat)",
                                                 min_value=0.0, format="%.2f",
                                                 key="gas_grundpreis")
            with col2:
                gas_end_m3 = st.number_input("Ende Zählerstand (m³)",
                                             min_value=0.0, format="%.3f",
                                             key="gas_end_m3")
                gas_arbeitspreis = st.number_input("Arbeitspreis (€/kWh)",
                                                   min_value=0.0, format="%.3f",
                                                   key="gas_arbeitspreis")
            gas_limit_pm = st.number_input("Prepayment per month (€)", min_value=0.0,
                                           key="gas_limit")
            gas_is_pauschale = st.checkbox(
                "Pauschale — prepayment is a hard limit (no refund if unused, "
                "Nachzahlung if exceeded)",
                key="gas_is_pauschale",
            )

            gas_bill_days = max(1, (gas_bill_end - gas_bill_start).days + 1)
            calc = gas_calc_detail(
                gas_start_m3, gas_end_m3, gas_umrechnung, gas_arbeitspreis, gas_grundpreis,
                num_tenants, gas_bill_days, g_eff_days, gas_limit_pm,
                is_pauschale=gas_is_pauschale,
            )
            st.info(
                f"Verbrauch: **{calc['verbrauch_m3']:.3f} m³** = **{calc['verbrauch_kwh']:.2f} kWh**  ·  "
                f"Ihr Anteil: **{calc['cost_tenant']:.2f} €**  ·  "
                f"Vorauszahlung: **{calc['prepay']:.2f} €**  ·  "
                f"Nachzahlung: **{calc['nach']:.2f} €**"
            )
            gas_data = {
                "bill_period":         f"{gas_bill_start.strftime('%d.%m.%Y')} – {gas_bill_end.strftime('%d.%m.%Y')}",
                "bill_days":           gas_bill_days,
                "period":              f"{g_eff_start.strftime('%d.%m.%Y')} – {g_eff_end.strftime('%d.%m.%Y')}",
                "days":                g_eff_days,
                "num_tenants":         int(num_tenants),
                "monthly_limit":       gas_limit_pm,
                "start_m3":            gas_start_m3,
                "end_m3":              gas_end_m3,
                "umrechnungsfaktor":   gas_umrechnung,
                "arbeitspreis":        gas_arbeitspreis,
                "grundpreis_monthly":  gas_grundpreis,
                **calc,
                "cost":        calc["cost_tenant"],
                "limit":       calc["prepay"],
                "is_pauschale": bool(gas_is_pauschale),
            }

    # ── Kaltwasser ─────────────────────────────────────────────────
    if include_water:
        st.subheader("Kaltwasser (Cold Water)")

        _kalt_where = _meter_where("AND type='kalt'")
        _apt_kalt_meters = fetch(
            f"SELECT id, serial_number, description "
            f"FROM wasser_meters WHERE {_kalt_where} ORDER BY id",
        )
        kalt_meter_info = None
        if _apt_kalt_meters:
            if len(_apt_kalt_meters) == 1:
                km = _apt_kalt_meters[0]
            else:
                km = st.selectbox(
                    "Kaltwasserzähler",
                    _apt_kalt_meters,
                    format_func=lambda x: f"{x[1] or '—'} ({x[2] or '—'})",
                    key="kalt_meter_sel",
                )
            kalt_meter_info = {
                "meter_id":    km[0],
                "serial":      km[1] or "",
                "description": km[2] or "",
            }
            st.info(
                f"Kaltwasserzähler registriert: **{km[1] or '—'}**  ·  "
                f"{km[2] or '—'}"
            )
        else:
            st.caption(
                "ℹ️ No Kaltwasserzähler registered for this apartment — register one "
                "in the Apartments page to attach the Zählernummer to this billing."
            )

        col1, col2 = st.columns(2)
        with col1:
            water_bill_start = st.date_input("Billing period start",
                                             value=date.today().replace(month=1, day=1),
                                             min_value=date.today() - timedelta(days=365 * 20),
                                             key="water_start")
        with col2:
            water_bill_end = st.date_input("Billing period end",
                                           value=date.today().replace(month=12, day=31),
                                           key="water_end")

        water_eff = _effective(water_bill_start, water_bill_end)
        if water_eff is None:
            st.warning("Tenant's contract does not overlap with the water billing period.")
        else:
            w_auto_s, w_auto_e = water_eff
            _wk = (water_bill_start, water_bill_end)
            if st.session_state.get("_water_bill_key") != _wk:
                st.session_state["water_eff_start"] = w_auto_s
                st.session_state["water_eff_end"]   = w_auto_e
                st.session_state["_water_bill_key"] = _wk
            st.caption("Tenant's effective period (auto-detected, editable):")
            col1, col2 = st.columns(2)
            with col1:
                w_eff_start = st.date_input("Effective start",
                                            min_value=date.today() - timedelta(days=365 * 20),
                                            key="water_eff_start")
            with col2:
                w_eff_end = st.date_input("Effective end", key="water_eff_end")
            w_eff_days = max(1, (w_eff_end - w_eff_start).days + 1)
            st.caption(f"{w_eff_days} days")

            st.caption("Meter readings & tariff:")
            col1, col2 = st.columns(2)
            with col1:
                water_start_m3 = st.number_input("Anfang Wasserzählerstand (m³)",
                                                 min_value=0.0, format="%.3f",
                                                 key="water_start_m3")
                water_frischwasser = st.number_input("Frischwasser (€/m³)",
                                                     min_value=0.0, format="%.3f",
                                                     key="water_frischwasser")
            with col2:
                water_end_m3 = st.number_input("Ende Wasserzählerstand (m³)",
                                               min_value=0.0, format="%.3f",
                                               key="water_end_m3")
                water_abwasser = st.number_input("Abwasser (€/m³)",
                                                 min_value=0.0, format="%.3f",
                                                 key="water_abwasser")
            water_limit_pm = st.number_input("Prepayment per month (€)", min_value=0.0,
                                             key="water_limit")
            water_is_pauschale = st.checkbox(
                "Pauschale — prepayment is a hard limit (no refund if unused, "
                "Nachzahlung if exceeded)",
                key="water_is_pauschale",
            )

            water_bill_days = max(1, (water_bill_end - water_bill_start).days + 1)
            calc = water_calc_detail(
                water_start_m3, water_end_m3, water_frischwasser, water_abwasser,
                num_tenants, water_bill_days, w_eff_days, water_limit_pm,
                is_pauschale=water_is_pauschale,
            )
            st.info(
                f"Verbrauch: **{calc['verbrauch_m3']:.3f} m³**  ·  "
                f"Ihr Anteil: **{calc['cost_tenant']:.2f} €**  ·  "
                f"Vorauszahlung: **{calc['prepay']:.2f} €**  ·  "
                f"Nachzahlung: **{calc['nach']:.2f} €**"
            )
            water_data = {
                "bill_period":       f"{water_bill_start.strftime('%d.%m.%Y')} – {water_bill_end.strftime('%d.%m.%Y')}",
                "bill_days":         water_bill_days,
                "period":            f"{w_eff_start.strftime('%d.%m.%Y')} – {w_eff_end.strftime('%d.%m.%Y')}",
                "days":              w_eff_days,
                "num_tenants":       int(num_tenants),
                "monthly_limit":     water_limit_pm,
                "start_m3":          water_start_m3,
                "end_m3":            water_end_m3,
                "frischwasser_per_m3": water_frischwasser,
                "abwasser_per_m3":   water_abwasser,
                **calc,
                "cost":        calc["cost_tenant"],
                "limit":       calc["prepay"],
                "is_pauschale": bool(water_is_pauschale),
                "meter_serial":      kalt_meter_info["serial"]      if kalt_meter_info else "",
                "meter_description": kalt_meter_info["description"] if kalt_meter_info else "",
            }

    # ── Warmwasser ─────────────────────────────────────────────────
    if include_warmwater:
        st.subheader("Warmwasser (Hot Water)")

        _warm_where = _meter_where("AND type='warm'")
        _warm_meters = fetch(
            f"SELECT id, serial_number, description "
            f"FROM wasser_meters WHERE {_warm_where} ORDER BY id",
        )
        if not _warm_meters:
            st.warning(
                "No Warmwasserzähler registered for this apartment. "
                "Please add at least one in the Apartments page first."
            )
        else:
            col1, col2 = st.columns(2)
            with col1:
                ww_bill_start = st.date_input("Billing period start",
                                              value=date.today().replace(month=1, day=1),
                                              min_value=date.today() - timedelta(days=365 * 20),
                                              key="ww_start")
            with col2:
                ww_bill_end = st.date_input("Billing period end",
                                            value=date.today().replace(month=12, day=31),
                                            key="ww_end")

            ww_eff = _effective(ww_bill_start, ww_bill_end)
            if ww_eff is None:
                st.warning("Tenant's contract does not overlap with the Warmwasser billing period.")
            else:
                ww_auto_s, ww_auto_e = ww_eff
                _wwk = (ww_bill_start, ww_bill_end)
                if st.session_state.get("_ww_bill_key") != _wwk:
                    st.session_state["ww_eff_start"] = ww_auto_s
                    st.session_state["ww_eff_end"]   = ww_auto_e
                    st.session_state["_ww_bill_key"] = _wwk
                st.caption("Tenant's effective period (auto-detected, editable):")
                col1, col2 = st.columns(2)
                with col1:
                    ww_eff_start = st.date_input("Effective start",
                                                 min_value=date.today() - timedelta(days=365 * 20),
                                                 key="ww_eff_start")
                with col2:
                    ww_eff_end = st.date_input("Effective end", key="ww_eff_end")
                ww_eff_days = max(1, (ww_eff_end - ww_eff_start).days + 1)
                st.caption(f"{ww_eff_days} days")

                st.caption("Warmwasserzähler readings (sum across all meters):")
                hc1, hc2, hc3, hc4, hc5 = st.columns([2, 2, 1, 1, 1])
                hc1.caption("Zählernummer")
                hc2.caption("Description")
                hc3.caption("Anfang (m³)")
                hc4.caption("Ende (m³)")
                hc5.caption("Verbrauch (m³)")

                warm_meter_inputs = []
                for mid, ws_serial, ws_desc in _warm_meters:
                    c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
                    c1.markdown(f"**{ws_serial or '—'}**")
                    c2.markdown(ws_desc or "—")
                    with c3:
                        ws_start = st.number_input("Start", min_value=0.0, format="%.3f",
                                                   key=f"ww_start_{mid}",
                                                   label_visibility="collapsed")
                    with c4:
                        ws_end = st.number_input("End", min_value=0.0, format="%.3f",
                                                 key=f"ww_end_{mid}",
                                                 label_visibility="collapsed")
                    c5.markdown(f"{max(0.0, ws_end - ws_start):.3f}")
                    warm_meter_inputs.append({
                        "meter_id":    mid,
                        "serial":      ws_serial or "",
                        "description": ws_desc or "",
                        "start":       ws_start,
                        "end":         ws_end,
                    })

                st.caption("Pricing — €/m³ components are summed:")
                col1, col2, col3 = st.columns(3)
                with col1:
                    ww_frischwasser = st.number_input("Frischwasser (€/m³)",
                                                       min_value=0.0, format="%.3f",
                                                       key="ww_frischwasser")
                with col2:
                    ww_abwasser = st.number_input("Abwasser (€/m³)",
                                                   min_value=0.0, format="%.3f",
                                                   key="ww_abwasser")
                with col3:
                    ww_heizenergie = st.number_input(
                        "Heizenergie (€/m³)",
                        min_value=0.0, format="%.3f",
                        key="ww_heizenergie",
                        help="Cost to heat 1 m³ of water (from your heating bill, "
                             "or 0 if billed via Heizkosten section)."
                    )
                ww_limit_pm = st.number_input("Prepayment per month (€)", min_value=0.0,
                                              key="ww_limit")
                ww_is_pauschale = st.checkbox(
                    "Pauschale — prepayment is a hard limit (no refund if unused, "
                    "Nachzahlung if exceeded)",
                    key="ww_is_pauschale",
                )

                ww_bill_days = max(1, (ww_bill_end - ww_bill_start).days + 1)
                calc_ww = warmwasser_calc_detail(
                    warm_meter_inputs, ww_frischwasser, ww_abwasser, ww_heizenergie,
                    num_tenants, ww_bill_days, ww_eff_days, ww_limit_pm,
                    is_pauschale=ww_is_pauschale,
                )
                st.info(
                    f"Verbrauch: **{calc_ww['verbrauch_m3']:.3f} m³**  ·  "
                    f"Preis: **{calc_ww['cost_per_m3']:.3f} €/m³**  ·  "
                    f"Ihr Anteil: **{calc_ww['cost_tenant']:.2f} €**  ·  "
                    f"Vorauszahlung: **{calc_ww['prepay']:.2f} €**  ·  "
                    f"Nachzahlung: **{calc_ww['nach']:.2f} €**"
                )
                warmwater_data = {
                    "bill_period":         f"{ww_bill_start.strftime('%d.%m.%Y')} – {ww_bill_end.strftime('%d.%m.%Y')}",
                    "bill_days":           ww_bill_days,
                    "period":              f"{ww_eff_start.strftime('%d.%m.%Y')} – {ww_eff_end.strftime('%d.%m.%Y')}",
                    "days":                ww_eff_days,
                    "num_tenants":         int(num_tenants),
                    "monthly_limit":       ww_limit_pm,
                    "frischwasser_per_m3": ww_frischwasser,
                    "abwasser_per_m3":     ww_abwasser,
                    "heizenergie_per_m3":  ww_heizenergie,
                    **calc_ww,
                    "cost":         calc_ww["cost_tenant"],
                    "limit":        calc_ww["prepay"],
                    "is_pauschale": bool(ww_is_pauschale),
                }

    # ── Heizkosten ─────────────────────────────────────────────────
    if include_heiz:
        st.subheader("Heizkosten (Heizkostenverteiler)")

        apt_id = selected_apartment_id

        reg_meters = fetch(
            f"SELECT id, serial_number, description, unit_label, "
            f"COALESCE(conversion_factor, 1.0) "
            f"FROM heizung_meters WHERE {_meter_where()} ORDER BY id",
        ) if apt_id else []

        if not reg_meters:
            st.warning(
                "No Heizkostenverteiler registered for this tenant's apartment. "
                "Please add meters in the Apartments page first."
            )
        else:
            col1, col2 = st.columns(2)
            with col1:
                heiz_bill_start = st.date_input("Billing period start",
                                                value=date.today().replace(month=1, day=1),
                                                min_value=date.today() - timedelta(days=365*20),
                                                key="heiz_start")
            with col2:
                heiz_bill_end = st.date_input("Billing period end",
                                              value=date.today().replace(month=12, day=31),
                                              key="heiz_end")

            heiz_eff = _effective(heiz_bill_start, heiz_bill_end)
            if heiz_eff is None:
                st.warning("Tenant's contract does not overlap with the Heizkosten billing period.")
            else:
                h_auto_s, h_auto_e = heiz_eff
                _hk = (heiz_bill_start, heiz_bill_end)
                if st.session_state.get("_heiz_bill_key") != _hk:
                    st.session_state["heiz_eff_start"] = h_auto_s
                    st.session_state["heiz_eff_end"]   = h_auto_e
                    st.session_state["_heiz_bill_key"] = _hk
                st.caption("Tenant's effective period (auto-detected, editable):")
                col1, col2 = st.columns(2)
                with col1:
                    h_eff_start = st.date_input("Effective start",
                                                min_value=date.today() - timedelta(days=365*20),
                                                key="heiz_eff_start")
                with col2:
                    h_eff_end = st.date_input("Effective end", key="heiz_eff_end")
                h_eff_days = max(1, (h_eff_end - h_eff_start).days + 1)
                st.caption(f"{h_eff_days} days")

                heiz_price_kwh = st.number_input(
                    "Price (€/kWh) — same for all meters, from ISTA bill",
                    min_value=0.0, format="%.4f", key="heiz_price_kwh",
                )

                st.caption("Meter readings — conversion factor per Heizkörper from ISTA bill:")
                # Header row
                hc1, hc2, hc3, hc4, hc5 = st.columns([2, 2, 1, 1, 1])
                hc1.caption("Serial")
                hc2.caption("Description")
                hc3.caption("Start reading")
                hc4.caption("End reading")
                hc5.caption("Conv. factor (→kWh)")

                meter_inputs = []
                for mid, serial, desc, unit_label, default_factor in reg_meters:
                    c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
                    c1.markdown(f"**{serial}**")
                    c2.markdown(desc or "—")
                    with c3:
                        m_start = st.number_input("Start", min_value=0.0, format="%.3f",
                                                  key=f"heiz_start_{mid}",
                                                  label_visibility="collapsed")
                    with c4:
                        m_end = st.number_input("End", min_value=0.0, format="%.3f",
                                                key=f"heiz_end_{mid}",
                                                label_visibility="collapsed")
                    with c5:
                        m_factor = st.number_input("Conv. factor", min_value=0.0,
                                                   value=float(st.session_state.get(
                                                       f"heiz_factor_{mid}", default_factor)),
                                                   format="%.4f",
                                                   key=f"heiz_factor_{mid}",
                                                   label_visibility="collapsed")
                    meter_inputs.append({
                        "meter_id":          mid,
                        "serial":            serial,
                        "description":       desc or "",
                        "unit_label":        unit_label or "Einheiten",
                        "start":             m_start,
                        "end":               m_end,
                        "unit_price":        heiz_price_kwh,
                        "conversion_factor": m_factor,
                    })

                unit_label_display = reg_meters[0][3] if reg_meters else "Einheiten"
                heiz_limit_pm  = st.number_input("Prepayment per month (€)",
                                                 min_value=0.0, key="heiz_limit")
                heiz_is_pauschale = st.checkbox(
                    "Pauschale — prepayment is a hard limit (no refund if unused)",
                    key="heiz_is_pauschale",
                )

                heiz_bill_days = max(1, (heiz_bill_end - heiz_bill_start).days + 1)
                calc_h = heizung_calc_detail(
                    meter_inputs, num_tenants, heiz_bill_days, h_eff_days,
                    heiz_limit_pm, is_pauschale=heiz_is_pauschale,
                )
                st.info(
                    f"Gesamtverbrauch: **{calc_h['total_units']:.3f} {unit_label_display}**  ·  "
                    f"Gesamtkosten Wohnung: **{calc_h['total_cost_flat']:.2f} €**  ·  "
                    f"Ihr Anteil: **{calc_h['cost_tenant']:.2f} €**  ·  "
                    f"Vorauszahlung: **{calc_h['prepay']:.2f} €**  ·  "
                    f"Nachzahlung: **{calc_h['nach']:.2f} €**"
                )
                heiz_data = {
                    "bill_period":    f"{heiz_bill_start.strftime('%d.%m.%Y')} – {heiz_bill_end.strftime('%d.%m.%Y')}",
                    "bill_days":      heiz_bill_days,
                    "period":         f"{h_eff_start.strftime('%d.%m.%Y')} – {h_eff_end.strftime('%d.%m.%Y')}",
                    "days":           h_eff_days,
                    "num_tenants":    int(num_tenants),
                    "monthly_limit":  heiz_limit_pm,
                    "price_kwh":      heiz_price_kwh,
                    "unit_label":     unit_label_display,
                    "is_pauschale":   bool(heiz_is_pauschale),
                    **calc_h,
                    "cost":  calc_h["cost_tenant"],
                    "limit": calc_h["prepay"],
                }

    # ── Betriebskosten ─────────────────────────────────────────────
    if include_bk:
        st.subheader("Betriebskosten")
        _ml      = {i: date(2000, i, 1).strftime("%B") for i in range(1, 13)}
        _yr_opts = list(range(date.today().year + 1, date.today().year - 20, -1))
        _prev_yr = next((i for i, y in enumerate(_yr_opts) if y == date.today().year - 1), 0)

        st.caption("Billing period (month / year):")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            bk_s_month = st.selectbox("Start month", list(_ml.keys()),
                                      format_func=lambda m: _ml[m], index=0, key="bk_s_month")
        with col2:
            bk_s_year  = st.selectbox("Start year", _yr_opts, index=_prev_yr, key="bk_s_year")
        with col3:
            bk_e_month = st.selectbox("End month", list(_ml.keys()),
                                      format_func=lambda m: _ml[m], index=11, key="bk_e_month")
        with col4:
            bk_e_year  = st.selectbox("End year", _yr_opts, index=_prev_yr, key="bk_e_year")

        bk_bill_start = date(bk_s_year, bk_s_month, 1)
        bk_bill_end   = date(bk_e_year, bk_e_month, calendar.monthrange(bk_e_year, bk_e_month)[1])
        bk_eff = _effective(bk_bill_start, bk_bill_end)

        if bk_eff is None:
            st.warning("Tenant's contract does not overlap with the BK billing period.")
        else:
            b_auto_s, b_auto_e = bk_eff
            _bk = (bk_s_month, bk_s_year, bk_e_month, bk_e_year)
            if st.session_state.get("_bk_bill_key") != _bk:
                st.session_state["bk_eff_s_month"] = b_auto_s.month
                st.session_state["bk_eff_s_year"]  = b_auto_s.year
                st.session_state["bk_eff_e_month"] = b_auto_e.month
                st.session_state["bk_eff_e_year"]  = b_auto_e.year
                st.session_state["_bk_bill_key"]   = _bk

            st.caption("Tenant's effective period (auto-detected, editable):")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                be_s_month = st.selectbox("Eff. start month", list(_ml.keys()),
                                          format_func=lambda m: _ml[m], key="bk_eff_s_month")
            with col2:
                be_s_year  = st.selectbox("Eff. start year", _yr_opts, key="bk_eff_s_year")
            with col3:
                be_e_month = st.selectbox("Eff. end month", list(_ml.keys()),
                                          format_func=lambda m: _ml[m], key="bk_eff_e_month")
            with col4:
                be_e_year  = st.selectbox("Eff. end year", _yr_opts, key="bk_eff_e_year")

            b_eff_months = max(1, (be_e_year - be_s_year) * 12 + (be_e_month - be_s_month) + 1)
            st.caption(f"{b_eff_months} month{'s' if b_eff_months != 1 else ''}")

            bk_limit_pm = st.number_input("Prepayment per month (€)", min_value=0.0, key="bk_limit")
            bk_cost     = st.number_input("Total Betriebskosten for billing period (€)",
                                          min_value=0.0, key="bk_cost")
            _, bk_period_cost, bk_limit, bk_nach = betriebskosten_calc(
                bk_cost, num_tenants, b_eff_months, bk_bill_start, bk_bill_end,
                limit_per_month=bk_limit_pm
            )
            b_eff_start_date = date(be_s_year, be_s_month, 1)
            b_eff_end_date   = date(be_e_year, be_e_month,
                                    calendar.monthrange(be_e_year, be_e_month)[1])
            bk_num_months = max(1, (bk_e_year - bk_s_year) * 12 + (bk_e_month - bk_s_month) + 1)
            bk_data = {
                "bill_period":   f"{bk_bill_start.strftime('%d.%m.%Y')} – {bk_bill_end.strftime('%d.%m.%Y')}",
                "num_months":    bk_num_months,
                "period":        f"{b_eff_start_date.strftime('%d.%m.%Y')} – {b_eff_end_date.strftime('%d.%m.%Y')}",
                "months":        int(b_eff_months),
                "total_cost":    bk_cost,
                "cost":          bk_period_cost,
                "limit":         bk_limit,
                "nach":          bk_nach,
                "monthly_limit": bk_limit_pm,
                "num_tenants":   int(num_tenants),
            }

    # ── Zusätzliche Positionen ─────────────────────────────────────
    if include_extra:
        st.subheader("Zusätzliche Positionen")
        st.caption(
            "Add agreed charges or deductions (e.g. damage repairs, cleaning). "
            "Positive = tenant owes, negative = credit to tenant. "
            "Use these to document Kaution deductions."
        )

        # Show Kaution on file for reference (only if not yet returned)
        kaution_row = fetch("""
            SELECT kaution_amount, kaution_returned_date FROM contracts
            WHERE id=?
        """, (selected_contract_id,))
        kaution = (
            kaution_row[0][0]
            if kaution_row and kaution_row[0][0] and not kaution_row[0][1]
            else None
        )
        if kaution:
            deductions_total = sum(
                float(st.session_state.get(f"extra_amt_{iid}", 0))
                for iid in st.session_state["extra_item_ids"]
            )
            remaining = kaution - deductions_total
            st.info(
                f"Kaution on file: **{kaution:.2f} €**  ·  "
                f"Total deductions below: **{deductions_total:.2f} €**  ·  "
                f"Remaining Kaution: **{remaining:.2f} €**"
            )

        # Column headers
        if st.session_state["extra_item_ids"]:
            h1, h2, h3 = st.columns([4, 1.5, 0.5])
            h1.caption("Description")
            h2.caption("Amount (€)")

        to_delete = None
        for iid in list(st.session_state["extra_item_ids"]):
            col1, col2, col3 = st.columns([4, 1.5, 0.5])
            with col1:
                st.text_input("Description", key=f"extra_desc_{iid}",
                              label_visibility="collapsed")
            with col2:
                st.number_input("Amount (€)", key=f"extra_amt_{iid}",
                                format="%.2f", label_visibility="collapsed")
            with col3:
                if st.button("✕", key=f"extra_del_{iid}"):
                    to_delete = iid

        if to_delete is not None:
            st.session_state["extra_item_ids"].remove(to_delete)
            st.session_state.pop(f"extra_desc_{to_delete}", None)
            st.session_state.pop(f"extra_amt_{to_delete}", None)
            st.rerun()

        if st.button("+ Add line item", key="extra_add"):
            iid = st.session_state["extra_item_counter"]
            st.session_state["extra_item_ids"].append(iid)
            st.session_state["extra_item_counter"] += 1
            st.rerun()

        items = _collect_extra_items()
        if items:
            total_extra = sum(i["amount"] for i in items)
            st.markdown(f"**Subtotal: {total_extra:.2f} €**")
            extra_data = {"items": items}

    # ── Generate PDF ───────────────────────────────────────────────
    st.divider()
    include_landlord_info = st.checkbox(
        "Include landlord info (address, IBAN, bank) in PDF",
        key="include_ll_info",
    )

    # Check for an unreturned Kaution on the selected contract
    kaution_row = fetch("""
        SELECT kaution_amount, kaution_returned_date FROM contracts
        WHERE id=?
    """, (selected_contract_id,))
    kaution_available = (
        kaution_row
        and kaution_row[0][0]
        and not kaution_row[0][1]   # not yet returned
    )
    kaution_amount = float(kaution_row[0][0]) if kaution_available else None

    deduct_from_kaution = False
    if kaution_available:
        deduct_from_kaution = st.checkbox(
            f"Deduct Nachzahlung from deposit (Kaution on file: {kaution_amount:.2f} €)",
            key="deduct_kaution",
        )
        if deduct_from_kaution:
            st.caption(
                "The PDF will show a Kautionsverrechnung block instead of a payment request. "
                "If the Nachzahlung exceeds the Kaution, the remaining balance is still shown as payable."
            )

    if st.button("Generate PDF"):
        if not any([strom_data, gas_data, water_data, warmwater_data,
                    heiz_data, bk_data, extra_data]):
            st.warning("Please select at least one cost type.")
        else:
            ll_info = None
            if include_landlord_info:
                ll_info = {
                    "address": get_config("landlord_address", ""),
                    "iban":    get_config("landlord_iban", ""),
                    "bank":    get_config("landlord_bank", ""),
                }
            kaution_info = {"kaution_amount": kaution_amount} if deduct_from_kaution else None
            file = invoice_pdf(
                tenant, address,
                landlord_name=landlord_name,
                gender=gender,
                signature_path=sig_path if Path(sig_path).exists() else None,
                strom=strom_data,
                gas=gas_data,
                water=water_data,
                warmwater=warmwater_data,
                heizung=heiz_data,
                bk=bk_data,
                extra=extra_data,
                kaution_info=kaution_info,
                landlord_info=ll_info,
                co_tenants=co_tenants if co_tenants else None,
            )
            with open(file, "rb") as f:
                st.download_button("Download PDF", f, file_name=file)

    # ── Save / Update Billing Profile ─────────────────────────────
    def _build_profile_data():
        pd_ = {"num_tenants": int(num_tenants), "contract_id": selected_contract_id}
        if include_strom and strom_data:
            pd_["strom"] = {
                "bill_start":          str(st.session_state["strom_start"]),
                "bill_end":            str(st.session_state["strom_end"]),
                "eff_start":           str(st.session_state["strom_eff_start"]),
                "eff_end":             str(st.session_state["strom_eff_end"]),
                "prepay_pm":           float(st.session_state.get("strom_limit", 0)),
                "start_kwh":           float(st.session_state.get("strom_start_kwh", 0)),
                "end_kwh":             float(st.session_state.get("strom_end_kwh", 0)),
                "arbeitspreis":        float(st.session_state.get("strom_arbeitspreis", 0)),
                "grundpreis_monthly":  float(st.session_state.get("strom_grundpreis", 0)),
                "is_pauschale":        bool(st.session_state.get("strom_is_pauschale", False)),
            }
        if include_gas and gas_data:
            pd_["gas"] = {
                "bill_start":          str(st.session_state["gas_start"]),
                "bill_end":            str(st.session_state["gas_end"]),
                "eff_start":           str(st.session_state["gas_eff_start"]),
                "eff_end":             str(st.session_state["gas_eff_end"]),
                "prepay_pm":           float(st.session_state.get("gas_limit", 0)),
                "start_m3":            float(st.session_state.get("gas_start_m3", 0)),
                "end_m3":              float(st.session_state.get("gas_end_m3", 0)),
                "umrechnungsfaktor":   float(st.session_state.get("gas_umrechnung", 10.0)),
                "arbeitspreis":        float(st.session_state.get("gas_arbeitspreis", 0)),
                "grundpreis_monthly":  float(st.session_state.get("gas_grundpreis", 0)),
                "is_pauschale":        bool(st.session_state.get("gas_is_pauschale", False)),
            }
        if include_water and water_data:
            pd_["water"] = {
                "bill_start":          str(st.session_state["water_start"]),
                "bill_end":            str(st.session_state["water_end"]),
                "eff_start":           str(st.session_state["water_eff_start"]),
                "eff_end":             str(st.session_state["water_eff_end"]),
                "prepay_pm":           float(st.session_state.get("water_limit", 0)),
                "start_m3":            float(st.session_state.get("water_start_m3", 0)),
                "end_m3":              float(st.session_state.get("water_end_m3", 0)),
                "frischwasser_per_m3": float(st.session_state.get("water_frischwasser", 0)),
                "abwasser_per_m3":     float(st.session_state.get("water_abwasser", 0)),
                "is_pauschale":        bool(st.session_state.get("water_is_pauschale", False)),
            }
        if include_warmwater and warmwater_data:
            pd_["warmwater"] = {
                "bill_start":          str(st.session_state["ww_start"]),
                "bill_end":            str(st.session_state["ww_end"]),
                "eff_start":           str(st.session_state["ww_eff_start"]),
                "eff_end":             str(st.session_state["ww_eff_end"]),
                "prepay_pm":           float(st.session_state.get("ww_limit", 0)),
                "frischwasser_per_m3": float(st.session_state.get("ww_frischwasser", 0)),
                "abwasser_per_m3":     float(st.session_state.get("ww_abwasser", 0)),
                "heizenergie_per_m3":  float(st.session_state.get("ww_heizenergie", 0)),
                "is_pauschale":        bool(st.session_state.get("ww_is_pauschale", False)),
                "meters": [
                    {
                        "meter_id":    m["meter_id"],
                        "serial":      m["serial"],
                        "description": m["description"],
                        "start":       float(st.session_state.get(f"ww_start_{m['meter_id']}", 0)),
                        "end":         float(st.session_state.get(f"ww_end_{m['meter_id']}", 0)),
                    }
                    for m in warm_meter_inputs
                ],
            }
        if include_bk and bk_data:
            pd_["bk"] = {
                "bill_s_month":  int(st.session_state["bk_s_month"]),
                "bill_s_year":   int(st.session_state["bk_s_year"]),
                "bill_e_month":  int(st.session_state["bk_e_month"]),
                "bill_e_year":   int(st.session_state["bk_e_year"]),
                "eff_s_month":   int(st.session_state["bk_eff_s_month"]),
                "eff_s_year":    int(st.session_state["bk_eff_s_year"]),
                "eff_e_month":   int(st.session_state["bk_eff_e_month"]),
                "eff_e_year":    int(st.session_state["bk_eff_e_year"]),
                "prepay_pm":     float(st.session_state.get("bk_limit", 0)),
                "total_cost":    float(st.session_state.get("bk_cost", 0)),
            }
        if include_heiz and heiz_data:
            pd_["heizung"] = {
                "bill_start":   str(st.session_state["heiz_start"]),
                "bill_end":     str(st.session_state["heiz_end"]),
                "eff_start":    str(st.session_state["heiz_eff_start"]),
                "eff_end":      str(st.session_state["heiz_eff_end"]),
                "prepay_pm":    float(st.session_state.get("heiz_limit", 0)),
                "price_kwh":    float(st.session_state.get("heiz_price_kwh", 0)),
                "is_pauschale": bool(st.session_state.get("heiz_is_pauschale", False)),
                "meters": [
                    {
                        "meter_id":          m["meter_id"],
                        "serial":            m["serial"],
                        "description":       m["description"],
                        "start":             float(st.session_state.get(f"heiz_start_{m['meter_id']}", 0)),
                        "end":               float(st.session_state.get(f"heiz_end_{m['meter_id']}", 0)),
                        "conversion_factor": float(st.session_state.get(f"heiz_factor_{m['meter_id']}", 1.0)),
                    }
                    for m in meter_inputs
                ],
            }
        extra_items = _collect_extra_items()
        if extra_items:
            pd_["extra_items"] = extra_items
        return pd_

    with st.expander("Save / Update Billing Profile"):
        save_mode = st.radio("Action", ["Save as new profile", "Update existing profile"],
                             horizontal=True, key="profile_save_mode", label_visibility="collapsed")

        if save_mode == "Save as new profile":
            profile_label = st.text_input("Profile label (e.g. '2023 Abrechnung')",
                                          key="profile_label")
            if st.button("Save", key="btn_save_profile"):
                pd_ = _build_profile_data()
                if len(pd_) <= 1:
                    st.warning("No billing data to save. Select at least one cost type first.")
                elif not profile_label.strip():
                    st.warning("Please enter a profile label.")
                else:
                    execute(
                        "INSERT INTO billing_profiles (tenant_id, label, created_date, data) "
                        "VALUES (?, ?, ?, ?)",
                        (tenant_choice[0], profile_label.strip(), str(date.today()),
                         json.dumps(pd_))
                    )
                    st.success(f"Profile '{profile_label}' saved.")
                    st.rerun()

        else:  # Update existing
            profiles_for_update = fetch(
                "SELECT id, label, created_date FROM billing_profiles "
                "WHERE tenant_id=? ORDER BY created_date DESC",
                (tenant_choice[0],)
            )
            if not profiles_for_update:
                st.info("No saved profiles for this tenant yet.")
            else:
                to_update = st.selectbox(
                    "Select profile to overwrite",
                    profiles_for_update,
                    format_func=lambda x: f"{x[1]}  ({x[2]})",
                    key="profile_update_sel",
                )
                if st.session_state.get("_profile_update_id") != to_update[0]:
                    st.session_state["_profile_update_id"]  = to_update[0]
                    st.session_state["profile_update_label"] = to_update[1]
                new_label = st.text_input("Rename (optional)",
                                          key="profile_update_label")
                if st.button("Update", key="btn_update_profile", type="primary"):
                    pd_ = _build_profile_data()
                    if len(pd_) <= 1:
                        st.warning("No billing data to save. Select at least one cost type first.")
                    else:
                        execute(
                            "UPDATE billing_profiles SET label=?, created_date=?, data=? WHERE id=?",
                            (new_label.strip() or to_update[1], str(date.today()),
                             json.dumps(pd_), to_update[0])
                        )
                        st.success(f"Profile '{new_label or to_update[1]}' updated.")
                        st.rerun()
