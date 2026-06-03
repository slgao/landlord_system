"""
One-shot migration: copy all data from SQLite → PostgreSQL.
Run once: python utils/migrate_sqlite_to_pg.py
"""

import sqlite3
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = "data/landlord.db"
DATABASE_URL = os.environ["DATABASE_URL"]

# Tables in dependency order (parents before children)
TABLES = [
    "properties",
    "apartments",
    "tenants",
    "contracts",
    "payments",
    "flat_costs",
    "reminders",
    "heizung_meters",
    "gas_meters",
    "co_tenants",
    "billing_profiles",
    "config",
]


def get_columns(sqlite_cur, table):
    sqlite_cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in sqlite_cur.fetchall()]


def migrate():
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    sc = src.cursor()

    dst = psycopg2.connect(DATABASE_URL)
    dc = dst.cursor()

    for table in TABLES:
        sc.execute(f"SELECT COUNT(*) FROM {table}")
        count = sc.fetchone()[0]
        if count == 0:
            print(f"  {table}: empty, skipping")
            continue

        cols = get_columns(sc, table)
        col_list = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))

        # Clear existing data in Postgres (safe for fresh migration)
        dc.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")

        sc.execute(f"SELECT {col_list} FROM {table}")
        rows = sc.fetchall()

        dc.executemany(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
            [tuple(r) for r in rows],
        )

        # Reset sequence to max(id) so future inserts don't collide
        if "id" in cols:
            dc.execute(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE(MAX(id), 1)
                ) FROM {table}
            """)

        dst.commit()
        print(f"  {table}: {len(rows)} rows migrated")

    src.close()
    dst.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    migrate()
