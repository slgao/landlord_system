import streamlit as st
import pandas as pd
import calendar
from datetime import date
from db import fetch


# ── helpers ───────────────────────────────────────────────────────────────────

def _expected_rent(prop_id, m_start, m_end):
    """Sum of contracted rent for all contracts active during the given month.
    Terminated contracts are included — their end_date already caps the active period."""
    rows = fetch("""
        SELECT c.rent FROM contracts c
        JOIN apartments a ON c.apartment_id = a.id
        WHERE a.property_id = ?
          AND c.start_date <= ?
          AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= ?)
    """, (prop_id, m_end, m_start))
    return sum(r[0] for r in rows)


def _actual_income(prop_id, m_start, m_end):
    """Sum of payments actually received in a month."""
    return fetch("""
        SELECT COALESCE(SUM(p.amount), 0)
        FROM payments p
        JOIN contracts c ON p.contract_id = c.id
        JOIN apartments a ON c.apartment_id = a.id
        WHERE a.property_id = ? AND p.payment_date BETWEEN ? AND ?
    """, (prop_id, m_start, m_end))[0][0]


def _flat_costs_month(prop_id, m_start, m_end, y, m):
    """Monthly cost equivalent for a property in a given month."""
    rows = fetch("""
        SELECT fc.amount, fc.frequency, fc.valid_from
        FROM flat_costs fc
        JOIN apartments a ON fc.apartment_id = a.id
        WHERE a.property_id = ?
          AND fc.valid_from <= ?
          AND (fc.valid_to IS NULL OR fc.valid_to = 'None' OR fc.valid_to >= ?)
    """, (prop_id, m_end, m_start))
    total = 0.0
    for amt, freq, vf in rows:
        if freq == "monthly":
            total += amt
        elif freq == "annual":
            total += amt / 12
        elif freq == "one-time" and vf and vf[:7] == f"{y}-{m:02d}":
            total += amt
    return total


def _color_net(val):
    return "color: #27ae60; font-weight:bold" if val >= 0 else "color: #e74c3c; font-weight:bold"


def _metric_html(label, value, sub=None, color="#ffffff"):
    sub_html = f"<div style='color:#8395a7;font-size:0.78em;margin-top:2px;'>{sub}</div>" if sub else ""
    return (
        f"<div style='background:#1e2d3d;border-radius:6px;padding:10px 14px;"
        f"border-left:4px solid #3a7fc1;'>"
        f"<div style='color:#9ec5e8;font-size:0.78em;'>{label}</div>"
        f"<div style='color:{color};font-size:1.15em;font-weight:bold;margin-top:2px;'>{value}</div>"
        f"{sub_html}</div>"
    )


def show():
    st.header("Balance Sheet")

    today  = date.today()
    year   = st.selectbox("Year", list(range(today.year + 1, today.year - 6, -1)),
                          index=1)   # default to current year
    y      = int(year)

    properties = fetch("SELECT id, name FROM properties ORDER BY name")
    if not properties:
        st.warning("No properties found.")
        return

    # ═══════════════════════════════════════════════════════════════
    # CURRENT SNAPSHOT  (always based on today, independent of year)
    # ═══════════════════════════════════════════════════════════════
    st.subheader("Current monthly snapshot")
    snap_start = str(today.replace(day=1))
    snap_end   = str(today.replace(day=calendar.monthrange(today.year, today.month)[1]))

    snap_cols = st.columns(len(properties) if len(properties) <= 4 else 4)
    for i, (pid, pname) in enumerate(properties):
        exp   = _expected_rent(pid, snap_start, snap_end)
        costs = _flat_costs_month(pid, snap_start, snap_end, today.year, today.month)
        net   = exp - costs
        col   = snap_cols[i % 4]
        net_color = "#27ae60" if net >= 0 else "#e74c3c"
        col.markdown(
            _metric_html(pname,
                         f"{net:+.2f} €",
                         f"Rent {exp:.2f} € − Costs {costs:.2f} €",
                         net_color),
            unsafe_allow_html=True,
        )

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # PER-PROPERTY ANNUAL VIEW
    # ═══════════════════════════════════════════════════════════════
    max_month = today.month if y == today.year else 12

    for prop_id, prop_name in properties:
        st.subheader(prop_name)

        # ── Monthly table ──────────────────────────────────────────
        rows            = []
        tot_expected    = tot_actual = tot_costs = 0.0

        for m in range(1, max_month + 1):
            m_start = f"{y}-{m:02d}-01"
            m_end   = f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"

            expected = _expected_rent(prop_id, m_start, m_end)
            actual   = _actual_income(prop_id, m_start, m_end)
            costs    = _flat_costs_month(prop_id, m_start, m_end, y, m)
            variance = actual - expected

            tot_expected += expected
            tot_actual   += actual
            tot_costs    += costs

            rows.append({
                "Month":              date(y, m, 1).strftime("%b %Y"),
                "Expected rent (€)":  round(expected, 2),
                "Actual received (€)":round(actual, 2),
                "Variance (€)":       round(variance, 2),
                "Costs (€)":          round(costs, 2),
                "Expected net (€)":   round(expected - costs, 2),
                "Actual net (€)":     round(actual - costs, 2),
            })

        df = pd.DataFrame(rows)
        st.dataframe(
            df.style
              .map(_color_net, subset=["Expected net (€)", "Actual net (€)"])
              .map(lambda v: "color:#e74c3c" if v < 0 else "color:#27ae60",
                   subset=["Variance (€)"]),
            use_container_width=True,
            hide_index=True,
        )

        # ── Annual metrics ─────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected rent",    f"€ {tot_expected:,.2f}")
        c2.metric("Actual received",  f"€ {tot_actual:,.2f}",
                  delta=f"{tot_actual - tot_expected:+.2f} vs expected")
        c3.metric("Total costs",      f"€ {tot_costs:,.2f}")
        c4.metric("Net (actual)",     f"€ {tot_actual - tot_costs:,.2f}",
                  delta=f"Expected {tot_expected - tot_costs:+.2f} €")

        # ── Per-flat breakdown ─────────────────────────────────────
        y_start = f"{y}-01-01"
        y_end   = f"{y}-{max_month:02d}-{calendar.monthrange(y, max_month)[1]:02d}"

        with st.expander(f"Per-flat breakdown ({y})"):
            apts = fetch("""
                SELECT a.id, a.name, a.flat FROM apartments a
                WHERE a.property_id = ? ORDER BY a.flat, a.name
            """, (prop_id,))

            # Group apartments by flat label; apartments without a flat label
            # are each their own group
            groups = {}
            for apt_id, apt_name, flat in apts:
                key = flat.strip() if flat and flat.strip() else f"\x00{apt_id}"
                groups.setdefault(key, []).append((apt_id, apt_name, flat))

            flat_rows    = []
            group_detail = []   # parallel list for per-flat payment breakdowns

            for key, members in groups.items():
                is_wg      = len(members) > 1
                flat_label = members[0][2] or members[0][1]

                total_rent     = 0.0
                total_received = 0.0
                total_costs    = 0.0
                apt_ids        = [m[0] for m in members]

                # Per-apartment: rent, received payments, costs
                for apt_id, apt_name, _ in members:
                    rent_row = fetch("""
                        SELECT c.rent FROM contracts c
                        WHERE c.apartment_id = ?
                          AND COALESCE(c.terminated, 0) = 0
                          AND c.start_date <= ?
                          AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= ?)
                        ORDER BY c.start_date DESC LIMIT 1
                    """, (apt_id, str(today), str(today)))
                    if rent_row:
                        total_rent += rent_row[0][0]

                    rec = fetch("""
                        SELECT COALESCE(SUM(p.amount), 0)
                        FROM payments p
                        JOIN contracts c ON p.contract_id = c.id
                        WHERE c.apartment_id = ? AND p.payment_date BETWEEN ? AND ?
                    """, (apt_id, y_start, y_end))
                    total_received += rec[0][0] if rec else 0.0

                    costs = fetch("""
                        SELECT fc.amount, fc.frequency FROM flat_costs fc
                        WHERE fc.apartment_id = ?
                          AND fc.valid_from <= ?
                          AND (fc.valid_to IS NULL OR fc.valid_to = 'None' OR fc.valid_to >= ?)
                          AND fc.frequency != 'one-time'
                    """, (apt_id, str(today), str(today)))
                    total_costs += sum(
                        r[0] if r[1] == "monthly" else r[0] / 12 for r in costs
                    )

                # Tenants whose contracts overlapped with the selected year
                ph = ",".join("?" * len(apt_ids))
                year_tenant_rows = fetch(f"""
                    SELECT DISTINCT t.name,
                           MAX(CASE WHEN COALESCE(c.terminated, 0) = 0
                                         AND (c.end_date IS NULL OR c.end_date = 'None'
                                              OR c.end_date >= ?)
                                    THEN 1 ELSE 0 END) AS still_active
                    FROM contracts c
                    JOIN tenants t ON c.tenant_id = t.id
                    WHERE c.apartment_id IN ({ph})
                      AND c.start_date <= ?
                      AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= ?)
                    GROUP BY t.name
                    ORDER BY t.name
                """, (str(today),) + tuple(apt_ids) + (y_end, y_start))
                year_tenants = {r[0]: bool(r[1]) for r in year_tenant_rows}

                # Also catch tenants with payments but no contract overlap found
                paid_rows = fetch(f"""
                    SELECT DISTINCT t.name
                    FROM payments p
                    JOIN contracts c ON p.contract_id = c.id
                    JOIN tenants t ON c.tenant_id = t.id
                    WHERE c.apartment_id IN ({ph})
                      AND p.payment_date BETWEEN ? AND ?
                    ORDER BY t.name
                """, tuple(apt_ids) + (y_start, y_end))
                for r in paid_rows:
                    if r[0] not in year_tenants:
                        year_tenants[r[0]] = False

                # Build display names
                all_names = [
                    name if still_active else f"{name} (moved out)"
                    for name, still_active in sorted(year_tenants.items())
                ]

                # Monthly payment breakdown for this flat (all rooms combined)
                ph = ",".join("?" * len(apt_ids))
                pay_detail = fetch(f"""
                    SELECT strftime('%Y-%m', p.payment_date) AS month,
                           t.name                            AS tenant,
                           SUM(p.amount)                     AS amount
                    FROM payments p
                    JOIN contracts c ON p.contract_id = c.id
                    JOIN tenants  t ON t.id = c.tenant_id
                    WHERE c.apartment_id IN ({ph})
                      AND p.payment_date BETWEEN ? AND ?
                    GROUP BY month, t.name
                    ORDER BY month, t.name
                """, tuple(apt_ids) + (y_start, y_end))

                tenant_str = ", ".join(all_names) if all_names else "— (vacant)"
                net = total_rent - total_costs
                flat_rows.append({
                    "Flat":               flat_label,
                    "Type":               "WG" if is_wg else "Wohnung",
                    "Tenant(s)":          tenant_str,
                    "Rent / mo (€)":      round(total_rent, 2),
                    f"Received {y} (€)":  round(total_received, 2),
                    "Costs / mo (€)":     round(total_costs, 2),
                    "Net / mo (€)":       round(net, 2),
                    "Net / yr  (€)":      round(net * 12, 2),
                })
                group_detail.append({
                    "label":  flat_label,
                    "is_wg":  is_wg,
                    "detail": pay_detail,
                })

            if flat_rows:
                received_col = f"Received {y} (€)"
                df_f = pd.DataFrame(flat_rows)
                st.dataframe(
                    df_f.style
                        .map(_color_net, subset=["Net / mo (€)", "Net / yr  (€)"])
                        .map(lambda v: "color:#27ae60" if v > 0 else "color:#8395a7",
                             subset=[received_col]),
                    use_container_width=True,
                    hide_index=True,
                )

                # ── Per-flat monthly payment detail ────────────────
                st.markdown("---")
                st.markdown(f"**Monthly payment breakdown — {y}**")
                for grp in group_detail:
                    st.caption(grp["label"] + (" (WG)" if grp["is_wg"] else ""))
                    rows = grp["detail"]
                    if not rows:
                        st.caption("  No payments recorded.")
                        continue

                    df_d = pd.DataFrame(rows, columns=["Month", "Tenant", "Amount (€)"])
                    # Pretty month label
                    df_d["Month"] = df_d["Month"].apply(
                        lambda s: date(int(s[:4]), int(s[5:7]), 1).strftime("%b %Y")
                    )
                    if grp["is_wg"]:
                        df_pivot = df_d.pivot_table(
                            index="Month", columns="Tenant",
                            values="Amount (€)", aggfunc="sum", fill_value=0,
                        ).reset_index()
                        tenant_cols = [c for c in df_pivot.columns if c != "Month"]
                        df_pivot["Total (€)"] = df_pivot[tenant_cols].sum(axis=1)
                        st.dataframe(df_pivot, use_container_width=True, hide_index=True)
                    else:
                        df_simple = (
                            df_d.groupby("Month", sort=False)["Amount (€)"]
                            .sum().reset_index()
                        )
                        st.dataframe(df_simple, use_container_width=True, hide_index=True)

                # ── Property totals ────────────────────────────────
                total_net_mo   = sum(r["Net / mo (€)"] for r in flat_rows)
                total_received = sum(r[received_col] for r in flat_rows)
                c1, c2 = st.columns(2)
                c1.markdown(
                    _metric_html(
                        f"Total received {y}",
                        f"{total_received:+.2f} €",
                        "Sum across all flats in this property",
                        "#27ae60" if total_received > 0 else "#8395a7",
                    ),
                    unsafe_allow_html=True,
                )
                c2.markdown(
                    _metric_html(
                        "Net / month (active contracts)",
                        f"{total_net_mo:+.2f} €",
                        f"Annual: {total_net_mo * 12:+.2f} €",
                        "#27ae60" if total_net_mo >= 0 else "#e74c3c",
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.info("No apartments found for this property.")

        st.divider()
