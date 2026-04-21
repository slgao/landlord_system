import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import fetch, execute


# ── Meter type configuration ──────────────────────────────────────────────────
# (label_for_radio, internal_meter_type, table, where_extra, unit, value_format)
METER_TYPES = [
    ("Strom",        "strom",   "strom_meters",  "",                 "kWh",        "%.2f"),
    ("Gas",          "gas",     "gas_meters",    "",                 "m³",         "%.3f"),
    ("Heizung",      "heizung", "heizung_meters", "",                "Einheiten",  "%.3f"),
    ("Kaltwasser",   "wasser",  "wasser_meters", "AND type='kalt'",  "m³",         "%.3f"),
    ("Warmwasser",   "wasser",  "wasser_meters", "AND type='warm'",  "m³",         "%.3f"),
]


def _flat_apt_in(apartment_id: int) -> str:
    """Return a SQL IN-list of all apartment IDs sharing the same flat label."""
    rows = fetch("""
        SELECT a2.id FROM apartments a2
        WHERE a2.property_id = (SELECT property_id FROM apartments WHERE id = ?)
          AND a2.flat IS NOT NULL AND a2.flat != ''
          AND a2.flat = (SELECT flat FROM apartments WHERE id = ?)
    """, (apartment_id, apartment_id))
    ids = [r[0] for r in rows] if rows else []
    if apartment_id not in ids:
        ids.append(apartment_id)
    return ",".join(str(i) for i in ids)


def _fetch_meters_for_apartment(apartment_id: int):
    """Return meters visible to this apartment, respecting scope:
    - 'room'   → only meters registered directly on this apartment_id
    - 'shared' → meters on any room in the same flat
    """
    apt_in = _flat_apt_in(apartment_id)
    out = []
    for label, mtype, table, where_extra, unit, vfmt in METER_TYPES:
        rows = fetch(
            f"SELECT id, serial_number, description "
            f"FROM {table} "
            f"WHERE ((COALESCE(scope,'room') = 'room' AND apartment_id = {apartment_id}) "
            f"    OR (scope = 'shared' AND apartment_id IN ({apt_in}))) "
            f"{where_extra} ORDER BY id",
        )
        for mid, serial, desc in rows:
            disp = f"{label}  ·  {serial or '—'}"
            if desc:
                disp += f" ({desc})"
            out.append({
                "type":    mtype,
                "id":      mid,
                "label":   label,
                "serial":  serial or "",
                "desc":    desc or "",
                "unit":    unit,
                "vfmt":    vfmt,
                "display": disp,
            })
    return out


def _fetch_readings(meter_type: str, meter_id: int):
    return fetch(
        "SELECT id, reading_date, reading, note "
        "FROM meter_readings WHERE meter_type=? AND meter_id=? "
        "ORDER BY reading_date, id",
        (meter_type, meter_id)
    )


def show():
    st.header("Meter Readings (Zählerstände)")
    st.caption(
        "Track meter readings over time, independent of the Nebenkostenabrechnung. "
        "Use this to monitor consumption trends and spot anomalies between billing cycles."
    )

    apt_data = fetch("""
        SELECT a.id, p.name, a.name, a.flat
        FROM apartments a
        JOIN properties p ON a.property_id = p.id
        ORDER BY p.name, a.flat, a.name
    """)
    if not apt_data:
        st.warning("No apartments yet. Create one in the Apartments page first.")
        return

    apt = st.selectbox(
        "Apartment", apt_data,
        format_func=lambda x: f"{x[2]}  ({x[1]}, flat: {x[3] or '—'})",
        key="mr_apt_sel",
    )
    apt_id = apt[0]

    meters = _fetch_meters_for_apartment(apt_id)
    if not meters:
        st.info(
            "No meters registered for this apartment. Register meters in the "
            "Apartments page (Heizkostenverteiler / Gaszähler / Stromzähler / "
            "Wasserzähler) first."
        )
        return

    # ── Add reading ──────────────────────────────────────────────────────────
    with st.expander("Add reading", expanded=True):
        m_choice = st.selectbox(
            "Meter", meters,
            format_func=lambda m: m["display"],
            key="mr_add_meter",
        )
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            r_date = st.date_input("Reading date", value=date.today(),
                                   min_value=date.today() - timedelta(days=365 * 20),
                                   key="mr_add_date")
        with col2:
            r_value = st.number_input(f"Reading ({m_choice['unit']})",
                                      min_value=0.0, format=m_choice["vfmt"],
                                      key="mr_add_value")
        with col3:
            r_note = st.text_input("Note (optional)", key="mr_add_note",
                                   placeholder="e.g. Jahresablesung, Zwischenstand")

        if st.button("Add reading", key="btn_mr_add"):
            existing = fetch(
                "SELECT 1 FROM meter_readings "
                "WHERE meter_type=? AND meter_id=? AND reading_date=?",
                (m_choice["type"], m_choice["id"], str(r_date))
            )
            if existing:
                st.warning(
                    f"A reading for this meter on {r_date} already exists. "
                    "Delete it first if you want to overwrite."
                )
            else:
                execute(
                    "INSERT INTO meter_readings "
                    "(meter_type, meter_id, reading_date, reading, note) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (m_choice["type"], m_choice["id"], str(r_date),
                     r_value, r_note.strip() or None)
                )
                st.success("Reading recorded.")
                st.rerun()

    st.divider()

    # ── Per-meter analysis ───────────────────────────────────────────────────
    st.subheader("Readings & consumption")

    for m in meters:
        rows = _fetch_readings(m["type"], m["id"])
        with st.expander(f"{m['display']}  ·  {len(rows)} reading(s)",
                         expanded=bool(rows)):
            if not rows:
                st.caption("No readings yet.")
                continue

            df = pd.DataFrame(rows, columns=["ID", "Date", "Reading", "Note"])
            df["Reading"] = df["Reading"].astype(float)
            df["Date_dt"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date_dt").reset_index(drop=True)

            df["Δ"]      = df["Reading"].diff()
            df["Days"]   = df["Date_dt"].diff().dt.days
            df["Avg/d"]  = df["Δ"] / df["Days"]

            display = df.assign(
                Reading=lambda d: d["Reading"].map(lambda v: format(v, m["vfmt"].lstrip("%"))),
                **{
                    "Δ":     df["Δ"].map(lambda v: "—" if pd.isna(v)
                                         else format(v, m["vfmt"].lstrip("%"))),
                    "Days":  df["Days"].map(lambda v: "—" if pd.isna(v) else f"{int(v)}"),
                    "Avg/d": df["Avg/d"].map(lambda v: "—" if pd.isna(v)
                                             else format(v, m["vfmt"].lstrip("%"))),
                }
            )[["ID", "Date", "Reading", "Δ", "Days", "Avg/d", "Note"]]
            display = display.rename(columns={
                "Reading": f"Reading ({m['unit']})",
                "Δ":       f"Δ ({m['unit']})",
                "Avg/d":   f"Avg/day ({m['unit']})",
            })
            st.dataframe(display, hide_index=True, width="stretch")

            # Summary metrics across the recorded period
            if len(df) >= 2:
                first, last = df.iloc[0], df.iloc[-1]
                total_days = max(1, (last["Date_dt"] - first["Date_dt"]).days)
                total_use  = last["Reading"] - first["Reading"]
                c1, c2, c3 = st.columns(3)
                c1.metric(f"Total since {first['Date']}",
                          f"{total_use:{m['vfmt'].lstrip('%')}} {m['unit']}")
                c2.metric("Days covered", f"{total_days}")
                c3.metric(f"Avg/day overall",
                          f"{total_use / total_days:{m['vfmt'].lstrip('%')}} {m['unit']}")

                chart_df = df[["Date_dt", "Reading"]].rename(
                    columns={"Date_dt": "Date"}).set_index("Date")
                st.line_chart(chart_df, height=200)

            # Delete control
            del_choice = st.selectbox(
                "Delete reading", rows,
                format_func=lambda r: f"#{r[0]} — {r[1]} — "
                                      f"{float(r[2]):{m['vfmt'].lstrip('%')}} {m['unit']}",
                key=f"mr_del_{m['type']}_{m['id']}",
            )
            if st.button("Delete selected reading",
                         key=f"btn_mr_del_{m['type']}_{m['id']}"):
                execute("DELETE FROM meter_readings WHERE id=?", (del_choice[0],))
                st.success("Reading deleted.")
                st.rerun()
