import streamlit as st
import pandas as pd
import calendar
from datetime import date
from db import fetch


# ── helpers ───────────────────────────────────────────────────────────────────

def _expected_rent(prop_id, m_start, m_end):
    """Sum of contracted rent for all active, non-terminated contracts in a month."""
    rows = fetch("""
        SELECT c.rent FROM contracts c
        JOIN apartments a ON c.apartment_id = a.id
        WHERE a.property_id = ?
          AND COALESCE(c.terminated, 0) = 0
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
        with st.expander("Per-flat breakdown (current active contracts)"):
            flats = fetch("""
                SELECT a.id, a.name, a.flat FROM apartments a
                WHERE a.property_id = ? ORDER BY a.flat, a.name
            """, (prop_id,))

            flat_rows = []
            for apt_id, apt_name, flat in flats:
                # active contract rent
                rent_row = fetch("""
                    SELECT c.rent, c.start_date, c.end_date, t.name
                    FROM contracts c JOIN tenants t ON t.id = c.tenant_id
                    WHERE c.apartment_id = ?
                      AND COALESCE(c.terminated, 0) = 0
                      AND c.start_date <= ?
                      AND (c.end_date IS NULL OR c.end_date = 'None' OR c.end_date >= ?)
                    ORDER BY c.start_date DESC LIMIT 1
                """, (apt_id, str(today), str(today)))

                rent    = rent_row[0][0] if rent_row else 0.0
                tenant  = rent_row[0][3] if rent_row else "—  (vacant)"

                apt_costs = fetch("""
                    SELECT fc.amount, fc.frequency FROM flat_costs fc
                    WHERE fc.apartment_id = ?
                      AND fc.valid_from <= ?
                      AND (fc.valid_to IS NULL OR fc.valid_to = 'None' OR fc.valid_to >= ?)
                      AND fc.frequency != 'one-time'
                """, (apt_id, str(today), str(today)))

                monthly_costs = sum(
                    r[0] if r[1] == "monthly" else r[0] / 12
                    for r in apt_costs
                )
                net = rent - monthly_costs
                flat_rows.append({
                    "Flat":             flat or "—",
                    "Room / Unit":      apt_name,
                    "Tenant":           tenant,
                    "Rent / mo (€)":    round(rent, 2),
                    "Costs / mo (€)":   round(monthly_costs, 2),
                    "Net / mo (€)":     round(net, 2),
                    "Net / yr  (€)":    round(net * 12, 2),
                })

            if flat_rows:
                df_f = pd.DataFrame(flat_rows)
                st.dataframe(
                    df_f.style.map(_color_net, subset=["Net / mo (€)", "Net / yr  (€)"]),
                    use_container_width=True,
                    hide_index=True,
                )
                total_net_mo = sum(r["Net / mo (€)"] for r in flat_rows)
                st.markdown(
                    _metric_html(
                        "Property net / month (active contracts only)",
                        f"{total_net_mo:+.2f} €",
                        f"Annual: {total_net_mo * 12:+.2f} €",
                        "#27ae60" if total_net_mo >= 0 else "#e74c3c",
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.info("No apartments found for this property.")

        st.divider()
