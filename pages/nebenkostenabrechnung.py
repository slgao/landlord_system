import streamlit as st
import calendar
from datetime import date, timedelta
from pathlib import Path
from db import fetch, get_tenant_address, get_tenant_gender
from logic import strom_calc, gas_calc, water_calc, betriebskosten_calc
from pdfgen import invoice_pdf


def show():
    st.header("Nebenkostenabrechnung")

    # ── Landlord & Signature ───────────────────────────────────────
    landlord_name = st.text_input("Landlord name", value="Ihr Vermieter")
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
    tenant  = tenant_choice[1]
    address = get_tenant_address(tenant) or ""
    gender  = get_tenant_gender(tenant)
    st.info(f"Address: {address}" if address else "No address found for this tenant.")

    # ── Auto-count persons in flat ─────────────────────────────────
    persons_in_flat = fetch("""
        SELECT COUNT(DISTINCT c.tenant_id)
        FROM contracts c
        JOIN apartments a ON c.apartment_id = a.id
        WHERE (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= date('now'))
        AND a.flat IS NOT NULL AND a.flat != ''
        AND a.property_id = (
            SELECT a2.property_id FROM contracts c2
            JOIN apartments a2 ON c2.apartment_id = a2.id
            JOIN tenants t ON c2.tenant_id = t.id
            WHERE t.name = ? LIMIT 1
        )
        AND a.flat = (
            SELECT a2.flat FROM contracts c2
            JOIN apartments a2 ON c2.apartment_id = a2.id
            JOIN tenants t ON c2.tenant_id = t.id
            WHERE t.name = ? AND (a2.flat IS NOT NULL AND a2.flat != '')
            LIMIT 1
        )
    """, (tenant, tenant))
    auto_count = persons_in_flat[0][0] if persons_in_flat and persons_in_flat[0][0] else 1

    st.divider()
    num_tenants = st.number_input("Tenants in flat", value=int(auto_count), min_value=1)
    if auto_count > 1:
        st.caption(f"ℹ️ Auto-detected {auto_count} active tenants sharing the same flat.")

    # ── Tenant contract reference ──────────────────────────────────
    st.divider()
    contract_row = fetch("""
        SELECT c.start_date, c.end_date FROM contracts c
        WHERE c.tenant_id=? ORDER BY c.start_date DESC LIMIT 1
    """, (tenant_choice[0],))
    if not contract_row:
        st.warning("No contract found for this tenant.")
        return

    c_start_str, c_end_str = contract_row[0]
    contract_start = date.fromisoformat(c_start_str)
    contract_end   = (date.fromisoformat(c_end_str)
                      if c_end_str and c_end_str != "None" else None)
    end_display = contract_end.strftime("%d.%m.%Y") if contract_end else "unbefristet"
    st.info(
        f"**Tenant contract:** {contract_start.strftime('%d.%m.%Y')} — {end_display}  \n"
        "Each utility's billing period is intersected with these dates to determine the effective share."
    )

    def _effective(bill_start, bill_end):
        c_end = contract_end if contract_end else bill_end
        eff_s = max(bill_start, contract_start)
        eff_e = min(bill_end, c_end)
        return (eff_s, eff_e) if eff_s <= eff_e else None

    # ── Cost type selection ────────────────────────────────────────
    st.divider()
    st.subheader("Select Cost Types to Include")
    include_strom = st.checkbox("Strom (Electricity)")
    include_gas   = st.checkbox("Gas")
    include_water = st.checkbox("Kaltwasser (Cold Water)")
    include_bk    = st.checkbox("Betriebskosten (Operating costs)")

    strom_data = gas_data = water_data = bk_data = None

    # ── Strom ──────────────────────────────────────────────────────
    if include_strom:
        st.subheader("Strom")
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
            s_eff_days = (s_eff_end - s_eff_start).days
            st.caption(f"{s_eff_days} days")

            strom_limit_pm = st.number_input("Prepayment per month (€)", min_value=0.0, key="strom_limit")
            strom_cost     = st.number_input("Total electricity cost for flat (€)", min_value=0.0, key="strom_cost")
            strom_bill_days = max(1, (strom_bill_end - strom_bill_start).days)
            _, s_limit, s_nach = strom_calc(strom_cost, num_tenants, strom_bill_days,
                                            s_eff_days, limit_per_month=strom_limit_pm)
            strom_data = {
                "bill_period": f"{strom_bill_start.strftime('%d.%m.%Y')} – {strom_bill_end.strftime('%d.%m.%Y')}",
                "bill_days":   strom_bill_days,
                "period":      f"{s_eff_start.strftime('%d.%m.%Y')} – {s_eff_end.strftime('%d.%m.%Y')}",
                "days":        s_eff_days,
                "cost":        strom_cost,
                "limit":       s_limit,
                "nach":        s_nach,
                "monthly_limit": strom_limit_pm,
                "num_tenants": int(num_tenants),
            }

    # ── Gas ────────────────────────────────────────────────────────
    if include_gas:
        st.subheader("Gas")
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
            g_eff_days = (g_eff_end - g_eff_start).days
            st.caption(f"{g_eff_days} days")

            gas_limit_pm = st.number_input("Prepayment per month (€)", min_value=0.0, key="gas_limit")
            gas_cost     = st.number_input("Total gas cost for flat (€)", min_value=0.0, key="gas_cost")
            gas_bill_days = max(1, (gas_bill_end - gas_bill_start).days)
            _, g_limit, g_nach = gas_calc(gas_cost, num_tenants, gas_bill_days,
                                          g_eff_days, limit_per_month=gas_limit_pm)
            gas_data = {
                "bill_period": f"{gas_bill_start.strftime('%d.%m.%Y')} – {gas_bill_end.strftime('%d.%m.%Y')}",
                "bill_days":   gas_bill_days,
                "period":      f"{g_eff_start.strftime('%d.%m.%Y')} – {g_eff_end.strftime('%d.%m.%Y')}",
                "days":        g_eff_days,
                "cost":        gas_cost,
                "limit":       g_limit,
                "nach":        g_nach,
                "monthly_limit": gas_limit_pm,
                "num_tenants": int(num_tenants),
            }

    # ── Kaltwasser ─────────────────────────────────────────────────
    if include_water:
        st.subheader("Kaltwasser (Cold Water)")
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
            w_eff_days = (w_eff_end - w_eff_start).days
            st.caption(f"{w_eff_days} days")

            water_limit_pm = st.number_input("Prepayment per month (€)", min_value=0.0, key="water_limit")
            water_cost     = st.number_input("Total cold water cost for flat (€)", min_value=0.0, key="water_cost")
            water_bill_days = max(1, (water_bill_end - water_bill_start).days)
            _, w_limit, w_nach = water_calc(water_cost, num_tenants, water_bill_days,
                                            w_eff_days, limit_per_month=water_limit_pm)
            water_data = {
                "bill_period": f"{water_bill_start.strftime('%d.%m.%Y')} – {water_bill_end.strftime('%d.%m.%Y')}",
                "bill_days":   water_bill_days,
                "period":      f"{w_eff_start.strftime('%d.%m.%Y')} – {w_eff_end.strftime('%d.%m.%Y')}",
                "days":        w_eff_days,
                "cost":        water_cost,
                "limit":       w_limit,
                "nach":        w_nach,
                "monthly_limit": water_limit_pm,
                "num_tenants": int(num_tenants),
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
                "bill_period": f"{bk_bill_start.strftime('%d.%m.%Y')} – {bk_bill_end.strftime('%d.%m.%Y')}",
                "num_months":  bk_num_months,
                "period":      f"{b_eff_start_date.strftime('%d.%m.%Y')} – {b_eff_end_date.strftime('%d.%m.%Y')}",
                "months":      int(b_eff_months),
                "total_cost":  bk_cost,
                "cost":        bk_period_cost,
                "limit":       bk_limit,
                "nach":        bk_nach,
                "monthly_limit": bk_limit_pm,
                "num_tenants": int(num_tenants),
            }

    # ── Generate PDF ───────────────────────────────────────────────
    if st.button("Generate PDF"):
        if not any([strom_data, gas_data, water_data, bk_data]):
            st.warning("Please select at least one cost type.")
        else:
            file = invoice_pdf(
                tenant, address,
                landlord_name=landlord_name,
                gender=gender,
                signature_path=sig_path if Path(sig_path).exists() else None,
                strom=strom_data,
                gas=gas_data,
                water=water_data,
                bk=bk_data,
            )
            with open(file, "rb") as f:
                st.download_button("Download PDF", f, file_name=file)
