import streamlit as st
import pandas as pd
from datetime import date
from db import fetch, insert, execute


# ── Status resolution ─────────────────────────────────────────────────────────

def _contract_status(end_date_str, terminated):
    """Return (status_key, label) for a single contract row."""
    if terminated:
        return "moved_out", "Moved out"
    if not end_date_str or end_date_str == "None":
        return "active", "Active"
    try:
        d = date.fromisoformat(end_date_str)
        days = (d - date.today()).days
        if days < 0:
            return "expired", "Expired — needs attention"
        if days <= 90:
            return "expiring", "Expiring soon"
        return "active", "Active"
    except ValueError:
        return "active", "Active"


_STATUS_PRIORITY = {"active": 0, "expiring": 1, "expired": 2, "moved_out": 3, "none": 4}


def _best_contract(contracts_for_tenant):
    """Pick the highest-priority contract for display."""
    if not contracts_for_tenant:
        return None
    return min(contracts_for_tenant, key=lambda r: _STATUS_PRIORITY[r["key"]])


def _row_style(status_key):
    if status_key == "expired":
        return "background-color: #c0392b; color: white"
    if status_key == "expiring":
        return "background-color: #e67e22; color: white"
    if status_key == "moved_out":
        return "color: #8395a7"
    return ""


def _build_tenant_rows():
    """Return one display row per tenant with resolved contract status."""
    tenants = fetch("SELECT id, name, email, gender FROM tenants ORDER BY name")
    if not tenants:
        return [], []

    contracts = fetch("""
        SELECT c.tenant_id, a.name, c.id, c.start_date, c.end_date,
               COALESCE(c.terminated, 0)
        FROM contracts c
        JOIN apartments a ON c.apartment_id = a.id
    """)

    # Group contracts by tenant_id
    by_tenant: dict = {}
    for r in contracts:
        tid = r[0]
        key, label = _contract_status(r[4], r[5])
        by_tenant.setdefault(tid, []).append({
            "apartment":  r[1],
            "contract_id": r[2],
            "start":      r[3],
            "end":        r[4] if r[4] and r[4] != "None" else "—",
            "key":        key,
            "label":      label,
        })

    active_rows, former_rows = [], []
    for tid, tname, temail, tgender in tenants:
        clist = by_tenant.get(tid, [])
        best  = _best_contract(clist)

        if best:
            row = {
                "ID":         tid,
                "Tenant":     tname,
                "Email":      temail or "—",
                "Apartment":  best["apartment"],
                "Contract":   f"#{best['contract_id']}",
                "Start":      best["start"],
                "End":        best["end"],
                "Status":     best["label"],
                "_key":       best["key"],
            }
            if best["key"] in ("active", "expiring"):
                active_rows.append(row)
            else:
                former_rows.append(row)
        else:
            active_rows.append({
                "ID":        tid,
                "Tenant":    tname,
                "Email":     temail or "—",
                "Apartment": "—",
                "Contract":  "—",
                "Start":     "—",
                "End":       "—",
                "Status":    "No contract",
                "_key":      "none",
            })

    return active_rows, former_rows


# ── Page ──────────────────────────────────────────────────────────────────────

def show():
    st.header("Tenants")

    active_rows, former_rows = _build_tenant_rows()
    all_rows = active_rows + former_rows

    # ── Active tenants ────────────────────────────────────────────────────────
    st.subheader(f"Active ({len(active_rows)})")
    if active_rows:
        df_a = pd.DataFrame(active_rows).drop(columns=["_key"])

        def _style_active(row):
            k = active_rows[row.name]["_key"]
            s = _row_style(k)
            return [s] * len(row)

        st.dataframe(
            df_a.style.apply(_style_active, axis=1),
            width="stretch", hide_index=True,
        )
        st.caption("🟠 Expiring within 90 days")
    else:
        st.info("No active tenants.")

    st.divider()

    # ── Former / attention needed ─────────────────────────────────────────────
    expired_count  = sum(1 for r in former_rows if r["_key"] == "expired")
    former_header  = f"Former / Inactive ({len(former_rows)})"
    if expired_count:
        former_header += f"  —  ⚠️ {expired_count} expired contract(s) need attention"

    st.subheader(former_header)
    if former_rows:
        df_f = pd.DataFrame(former_rows).drop(columns=["_key"])

        def _style_former(row):
            k = former_rows[row.name]["_key"]
            s = _row_style(k)
            return [s] * len(row)

        st.dataframe(
            df_f.style.apply(_style_former, axis=1),
            width="stretch", hide_index=True,
        )
        st.caption(
            "🔴 Expired — contract past end date, not yet resolved (go to Contracts → Handle Expired Contracts)  "
            "&nbsp;&nbsp; ⬜ Moved out — contract closed"
        )
    else:
        st.info("No former tenants.")

    st.divider()

    # ── Add Tenant ────────────────────────────────────────────────────────────
    with st.expander("Add Tenant"):
        name   = st.text_input("Name",  key="new_t_name")
        email  = st.text_input("Email", key="new_t_email")
        gender = st.selectbox("Gender", ["male", "female", "diverse"], key="new_t_gender")
        if st.button("Add Tenant", key="btn_add_tenant"):
            insert("tenants", (name, email, gender))
            st.success("Tenant added.")
            st.rerun()

    if all_rows:
        # Deduplicated tenant list for selectors
        all_tenants = fetch("SELECT id, name, email, gender FROM tenants ORDER BY name")

        with st.expander("Edit Tenant"):
            t = st.selectbox("Select tenant", all_tenants,
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
            cur_apt    = fetch(
                "SELECT apartment_id FROM contracts WHERE tenant_id=? "
                "ORDER BY start_date DESC LIMIT 1", (t[0],)
            )
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
                    execute("UPDATE contracts SET apartment_id=? WHERE tenant_id=? "
                            "AND start_date = (SELECT MAX(start_date) FROM contracts WHERE tenant_id=?)",
                            (new_apt[0], t[0], t[0]))
                st.success(f"Tenant '{new_name}' updated.")
                st.rerun()

        with st.expander("Delete Tenant"):
            to_del = st.selectbox("Select tenant", all_tenants,
                                  format_func=lambda x: f"#{x[0]} — {x[1]}",
                                  key="tenant_delete")
            st.warning("This will permanently remove the tenant.")
            if st.button("Delete Tenant", type="primary", key="btn_del_tenant"):
                execute("DELETE FROM tenants WHERE id=?", (to_del[0],))
                st.success(f"Tenant '{to_del[1]}' removed.")
                st.rerun()
