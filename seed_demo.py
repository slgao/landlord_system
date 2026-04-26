#!/usr/bin/env python3
"""
Demo data seeder for the Landlord Management System.
Seeds a realistic 2-property German portfolio into a separate demo database.

Usage
-----
    python seed_demo.py           # seed only if DB is empty
    python seed_demo.py --reset   # wipe all data and re-seed

Setup
-----
    1. Create a fresh PostgreSQL database, e.g.:
           createdb landlord_demo
    2. Copy the template and fill in the URL:
           cp .env.demo.example .env.demo
    3. Seed it:
           python seed_demo.py --reset
    4. Launch the app pointing at the demo DB:
           env $(grep ^DATABASE_URL .env.demo) streamlit run app.py
"""

import argparse
import os
import sys
from pathlib import Path


# ── Load .env.demo BEFORE importing db (db reads DATABASE_URL at import time) ──

def _load_env_file(path: str) -> None:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: {path} not found.\n"
              f"  cp .env.demo.example .env.demo  # then fill in your demo DB URL")
        sys.exit(1)
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip()   # always override


_load_env_file(".env.demo")

# ── Now safe to import db (uses the demo DATABASE_URL) ──────────────────────
from db import get_conn, init_db   # noqa: E402


# ── DB helper: INSERT … RETURNING id ────────────────────────────────────────

def _ins(cur, table: str, cols: list[str], vals: list) -> int:
    ph = ", ".join(["%s"] * len(vals))
    cur.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph}) RETURNING id",
        vals,
    )
    return cur.fetchone()[0]


# ── Reset: wipe all tables in child-first order ──────────────────────────────

_TABLES = [
    "billing_profiles", "co_tenants", "meter_readings",
    "heizung_meters", "gas_meters", "strom_meters", "wasser_meters",
    "reminders", "kaution_deductions", "flat_costs",
    "payments", "contracts", "tenants", "apartments", "properties", "config",
]


def _reset(cur) -> None:
    for t in _TABLES:
        cur.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
    print("  Wiped all tables.")


# ── Seed ─────────────────────────────────────────────────────────────────────

def seed(cur) -> dict:
    # ── Properties ──────────────────────────────────────────────────────────
    print("  Properties …")
    p_muc = _ins(cur, "properties", ["name", "address"],
                 ["Schillerstraße 8", "Schillerstraße 8, 80336 München"])
    p_ber = _ins(cur, "properties", ["name", "address"],
                 ["Goetheweg 3", "Goetheweg 3, 10115 Berlin"])

    # ── Apartments ──────────────────────────────────────────────────────────
    print("  Apartments …")
    a_eg = _ins(cur, "apartments", ["property_id", "name", "flat"],
                [p_muc, "Wohnung 1 EG", None])
    a_og = _ins(cur, "apartments", ["property_id", "name", "flat"],
                [p_muc, "Wohnung 2 OG", None])
    a_z1 = _ins(cur, "apartments", ["property_id", "name", "flat"],
                [p_muc, "Zimmer 1 DG", "WG Dachgeschoss"])
    a_z2 = _ins(cur, "apartments", ["property_id", "name", "flat"],
                [p_muc, "Zimmer 2 DG", "WG Dachgeschoss"])
    a_b1 = _ins(cur, "apartments", ["property_id", "name", "flat"],
                [p_ber, "Wohnung 1", None])
    a_b2 = _ins(cur, "apartments", ["property_id", "name", "flat"],
                [p_ber, "Wohnung 2", None])

    # ── Tenants ─────────────────────────────────────────────────────────────
    print("  Tenants …")
    T = ["name", "email", "gender"]
    t_anna   = _ins(cur, "tenants", T, ["Anna Müller",      "anna.mueller@example.de",    "female"])
    t_thomas = _ins(cur, "tenants", T, ["Thomas Schneider", "thomas.schneider@example.de","male"])
    t_julia  = _ins(cur, "tenants", T, ["Julia Weber",      "julia.weber@example.de",     "female"])
    t_markus = _ins(cur, "tenants", T, ["Markus Fischer",   "markus.fischer@example.de",  "male"])
    t_sarah  = _ins(cur, "tenants", T, ["Sarah Koch",       "sarah.koch@example.de",      "female"])
    t_lukas  = _ins(cur, "tenants", T, ["Lukas Bauer",      "lukas.bauer@example.de",     "male"])

    # ── Contracts ───────────────────────────────────────────────────────────
    print("  Contracts …")
    CC = [
        "tenant_id", "apartment_id", "rent", "start_date", "end_date",
        "kaution_amount", "kaution_paid_date",
        "kaution_returned_date", "kaution_returned_amount",
        "terminated", "currency", "kaution_currency",
    ]
    c_anna   = _ins(cur, "contracts", CC,
        [t_anna,   a_eg,  850.00, "2023-03-01", None,
         2550.00, "2023-02-20", None, None, 0, "EUR", "EUR"])
    c_thomas = _ins(cur, "contracts", CC,
        [t_thomas, a_og,  950.00, "2022-09-01", None,
         2850.00, "2022-08-25", None, None, 0, "EUR", "EUR"])
    c_julia  = _ins(cur, "contracts", CC,
        [t_julia,  a_z1,  550.00, "2024-01-01", None,
         1650.00, "2023-12-20", None, None, 0, "EUR", "EUR"])
    c_markus = _ins(cur, "contracts", CC,             # expiring soon (2026-06-30)
        [t_markus, a_z2,  480.00, "2024-01-01", "2026-06-30",
         1440.00, "2023-12-20", None, None, 0, "EUR", "EUR"])
    c_sarah  = _ins(cur, "contracts", CC,
        [t_sarah,  a_b1, 1100.00, "2023-06-01", None,
         3300.00, "2023-05-20", None, None, 0, "EUR", "EUR"])
    c_lukas  = _ins(cur, "contracts", CC,             # moved out Dec 2024
        [t_lukas,  a_b2,  800.00, "2022-01-01", "2024-12-31",
         2400.00, "2021-12-20", "2025-01-20", 2250.00, 1, "EUR", "EUR"])

    # ── Co-tenant (Thomas's partner) ─────────────────────────────────────────
    _ins(cur, "co_tenants",
         ["contract_id", "name", "gender", "email", "in_contract"],
         [c_thomas, "Laura Schneider", "female", "laura.schneider@example.de", 1])

    # ── Payments ─────────────────────────────────────────────────────────────
    print("  Payments …")

    def _months(y_start, m_start, n):
        """Generate n payment date strings (3rd of each month)."""
        y, m = y_start, m_start
        out = []
        for _ in range(n):
            out.append(f"{y:04d}-{m:02d}-03")
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return out

    # 12 months of recent history: May 2025 – Apr 2026
    recent = _months(2025, 5, 12)
    # Julia: skip Feb 2026 (one outstanding month → Mahnung demo)
    julia_months = [d for d in recent if d != "2026-02-03"]
    # Lukas: last 12 months before move-out (Jan – Dec 2024)
    lukas_months = _months(2024, 1, 12)

    PC = ["contract_id", "amount", "payment_date", "currency"]
    for d in recent:
        _ins(cur, "payments", PC, [c_anna,    850.00, d, "EUR"])
        _ins(cur, "payments", PC, [c_thomas,  950.00, d, "EUR"])
        _ins(cur, "payments", PC, [c_markus,  480.00, d, "EUR"])
        _ins(cur, "payments", PC, [c_sarah,  1100.00, d, "EUR"])
    for d in julia_months:
        _ins(cur, "payments", PC, [c_julia,   550.00, d, "EUR"])
    for d in lukas_months:
        _ins(cur, "payments", PC, [c_lukas,   800.00, d, "EUR"])

    # ── Payment reminder (Julia's missed Feb) ────────────────────────────────
    _ins(cur, "reminders",
         ["contract_id", "sent_date", "months_due", "amount_due", "channel", "note"],
         [c_julia, "2026-02-15", "2026-02", 550.00, "E-Mail",
          "Zahlungserinnerung für Februar 2026 versandt."])

    # ── Kaution deduction (Lukas moved out with cleaning charge) ────────────
    _ins(cur, "kaution_deductions",
         ["contract_id", "date", "amount", "category", "reason",
          "reference_type", "reference_id"],
         [c_lukas, "2025-01-10", 150.00, "Reinigung",
          "Endreinigung nicht professionell durchgeführt — Nachbesserung beauftragt.",
          None, None])

    # ── Flat Costs ───────────────────────────────────────────────────────────
    print("  Flat costs …")
    FC = ["apartment_id", "cost_type", "amount", "frequency", "valid_from", "valid_to"]
    _ins(cur, "flat_costs", FC, [a_eg, "Hausgeld",    185.00, "monthly",  "2023-01-01", None])
    _ins(cur, "flat_costs", FC, [a_eg, "Grundsteuer", 340.00, "annual",   "2023-01-01", None])
    _ins(cur, "flat_costs", FC, [a_og, "Hausgeld",    200.00, "monthly",  "2022-09-01", None])
    _ins(cur, "flat_costs", FC, [a_og, "Grundsteuer", 380.00, "annual",   "2022-09-01", None])
    _ins(cur, "flat_costs", FC, [a_z1, "Hausgeld",    110.00, "monthly",  "2024-01-01", None])
    _ins(cur, "flat_costs", FC, [a_z1, "Internet",     29.99, "monthly",  "2024-01-01", None])
    _ins(cur, "flat_costs", FC, [a_z2, "Hausgeld",    110.00, "monthly",  "2024-01-01", None])
    _ins(cur, "flat_costs", FC, [a_b1, "Hausgeld",    215.00, "monthly",  "2023-06-01", None])
    _ins(cur, "flat_costs", FC, [a_b1, "Grundsteuer", 295.00, "annual",   "2023-06-01", None])
    _ins(cur, "flat_costs", FC, [a_b2, "Hausgeld",    175.00, "monthly",  "2022-01-01", None])
    _ins(cur, "flat_costs", FC, [a_b2, "Grundsteuer", 250.00, "annual",   "2022-01-01", None])

    # ── Electricity meters + readings ────────────────────────────────────────
    print("  Electricity meters …")
    SM = ["apartment_id", "serial_number", "description", "scope"]
    sm_eg = _ins(cur, "strom_meters", SM, [a_eg, "SM-EG-001", "Stromzähler EG",       "shared"])
    sm_og = _ins(cur, "strom_meters", SM, [a_og, "SM-OG-001", "Stromzähler OG",       "shared"])
    sm_z1 = _ins(cur, "strom_meters", SM, [a_z1, "SM-Z1-001", "Stromzähler Zimmer 1", "room"])
    sm_z2 = _ins(cur, "strom_meters", SM, [a_z2, "SM-Z2-001", "Stromzähler Zimmer 2", "room"])
    sm_b1 = _ins(cur, "strom_meters", SM, [a_b1, "SM-B1-001", "Stromzähler Berlin 1", "shared"])
    sm_b2 = _ins(cur, "strom_meters", SM, [a_b2, "SM-B2-001", "Stromzähler Berlin 2", "shared"])

    # 13 readings per meter: 2025-05-01 … 2026-05-01 (one per month)
    MR = ["meter_type", "meter_id", "reading_date", "reading", "note"]
    strom_cfg = [
        # (meter_id, start_kWh, monthly_kWh)
        (sm_eg, 12500.0, 272.0),
        (sm_og,  8200.0, 318.0),
        (sm_z1,  3400.0, 178.0),
        (sm_z2,  3100.0, 157.0),
        (sm_b1, 15000.0, 342.0),
        (sm_b2,  7800.0, 248.0),
    ]
    for meter_id, start, delta in strom_cfg:
        y, m, val = 2025, 5, start
        for _ in range(13):
            _ins(cur, "meter_readings", MR,
                 ["strom", meter_id, f"{y:04d}-{m:02d}-01", round(val, 1), None])
            val += delta
            m += 1
            if m > 12:
                m, y = 1, y + 1

    # ── Gas meter (WG flat, shared between both rooms) ───────────────────────
    print("  Gas meter …")
    gm_wg = _ins(cur, "gas_meters",
                 ["apartment_id", "serial_number", "description",
                  "z_zahl", "brennwert", "scope"],
                 [a_z1, "GZ-WG-001", "Gaszähler WG Dachgeschoss",
                  1.0, 10.55, "shared"])

    y, m, gas_val = 2025, 5, 8500.0
    for _ in range(13):
        _ins(cur, "meter_readings", MR,
             ["gas", gm_wg, f"{y:04d}-{m:02d}-01", round(gas_val, 1), None])
        gas_val += 32.5   # ~32.5 m³/month
        m += 1
        if m > 12:
            m, y = 1, y + 1

    # ── Heating meters (seasonal usage, München main apartments) ────────────
    print("  Heating meters …")
    HM = ["apartment_id", "serial_number", "description",
          "unit_price", "unit_label", "conversion_factor", "scope"]
    hm_eg = _ins(cur, "heizung_meters", HM,
                 [a_eg, "HZ-EG-001", "Heizkostenverteiler EG",
                  0.08, "Einheiten", 1.0, "room"])
    hm_og = _ins(cur, "heizung_meters", HM,
                 [a_og, "HZ-OG-001", "Heizkostenverteiler OG",
                  0.08, "Einheiten", 1.0, "room"])

    SEASONAL = {11: 90, 12: 105, 1: 105, 2: 90, 3: 45, 10: 40}  # month → delta
    y, m = 2025, 5
    hz_eg, hz_og = 1200.0, 1450.0
    for _ in range(13):
        _ins(cur, "meter_readings", MR,
             ["heizung", hm_eg, f"{y:04d}-{m:02d}-01", round(hz_eg, 1), None])
        _ins(cur, "meter_readings", MR,
             ["heizung", hm_og, f"{y:04d}-{m:02d}-01", round(hz_og, 1), None])
        delta = SEASONAL.get(m, 5)
        hz_eg += delta
        hz_og += round(delta * 1.2, 1)
        m += 1
        if m > 12:
            m, y = 1, y + 1

    return {
        "properties":     2,
        "apartments":     6,
        "tenants":        6,
        "contracts":      6,
        "payments":       len(recent) * 4 + len(julia_months) + len(lukas_months),
        "flat_costs":     11,
        "meter_readings": 13 * (len(strom_cfg) + 1 + 2),  # strom + gas + 2×heizung
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true",
                    help="Wipe all existing data before seeding")
    args = ap.parse_args()

    conn = get_conn()
    cur  = conn.cursor()

    print("Initialising tables …")
    init_db()   # idempotent — creates tables if they don't exist yet

    if not args.reset:
        cur.execute("SELECT COUNT(*) FROM properties")
        if cur.fetchone()[0] > 0:
            print("Database already contains data. Use --reset to wipe and re-seed.")
            conn.close()
            sys.exit(0)
    else:
        print("Resetting …")
        _reset(cur)

    print("Seeding …")
    stats = seed(cur)

    conn.commit()
    conn.close()

    print("\nDone! Rows inserted:")
    for k, v in stats.items():
        print(f"  {k:<18} {v}")

    print("\nLaunch the app against the demo DB:")
    print('  env $(grep ^DATABASE_URL .env.demo) streamlit run app.py')


if __name__ == "__main__":
    main()
