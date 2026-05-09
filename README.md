# Hausverwaltung

Property management for German landlords — rent tracking, utility billing, and PDF generation, all in one place.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.x-FF4B4B?logo=streamlit&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.x-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

![Dashboard](docs/screenshots/dashboard.png)

## What it does

Built to manage a handful of properties without paying for commercial landlord software. Covers the full rental lifecycle — from creating contracts and tracking monthly rent to generating legally-formatted PDFs at year end.

The heavy lifting:
- **Nebenkostenabrechnung** — calculates Strom, Gas, Wasser, Heizung, and Betriebskosten with correct day-based proration; handles partial occupancy and WG shared meters
- **Mahnung Generator** — formal payment reminder PDFs with gender-aware salutation and landlord signature
- **Kaution tracking** — log deductions (damage, cleaning, arrears), track the open balance, mark returned
- **Balance sheet** — monthly and annual P&L per property, with per-flat breakdown and occupancy rate

Also handles: multi-currency contracts (EUR/CNY/USD/GBP), co-tenants (Mitmieter), fixed-term and open-ended leases, meter reading history, flat costs (Hausgeld, mortgage, Grundsteuer).

---

## Screenshots

| Contracts | Rent Tracking |
|---|---|
| ![Contracts](docs/screenshots/contracts.png) | ![Rent Tracking](docs/screenshots/rent_tracking.png) |

| Balance Sheet | Nebenkostenabrechnung |
|---|---|
| ![Balance Sheet](docs/screenshots/balance_sheet.png) | ![Nebenkostenabrechnung](docs/screenshots/nebenkostenabrechnung.png) |

| Mahnung Generator | Meter Readings |
|---|---|
| ![Mahnung Generator](docs/screenshots/mahnung_generator.png) | ![Meter Readings](docs/screenshots/meter_readings.png) |

---

## Stack

| Layer | Tech |
|---|---|
| UI | Streamlit |
| API | FastAPI + Uvicorn |
| Database | PostgreSQL 16 (Docker locally, Neon in cloud) |
| Migrations | Alembic |
| PDFs | ReportLab |

---

## Getting started

**Prerequisites:** Python 3.10+, Docker Desktop

```bash
git clone https://github.com/slgao/landlord_system.git
cd landlord_system
cp .env.example .env        # set POSTGRES_PASSWORD
./setup.sh
```

`setup.sh` creates the virtualenv, pulls the Docker image, starts the container, and initialises the schema. Then:

```bash
source venv/bin/activate
honcho start
```

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| FastAPI | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### Daily use

The database container starts automatically with Docker Desktop (`--restart unless-stopped`). Your daily workflow is just:

```bash
source venv/bin/activate && honcho start
```

---

## Cloud database (Neon)

To share data across machines, point both at a [Neon](https://neon.tech) PostgreSQL instance instead of local Docker.

```bash
# One-time migration from local Docker to Neon
./scripts/migrate_to_neon.sh "postgresql://user:pass@host/neondb?sslmode=require"

# Sync local Docker from Neon (on any machine that's drifted)
./scripts/sync_local_from_neon.sh
```

Update `DATABASE_URL` in `.env` to your Neon connection string. Alembic runs automatically on startup — nothing else to do.

---

## Backups

`scripts/backup.sh` dumps Neon to a gzip file and keeps the last 30. Set it up once with cron:

```bash
(crontab -l 2>/dev/null; echo "CRON_TZ=Europe/Berlin"; echo "0 22 * * * $PWD/scripts/backup.sh >> $HOME/landlord_backups/backup.log 2>&1") | crontab -
```

---

## Migrating to a new machine

```bash
# On old machine — export
./scripts/dump_db.sh
scp backups/*.sql user@new-host:~/landlord_system/backups/

# On new machine — after ./setup.sh
./scripts/restore_db.sh
```

---

## Project layout

```
landlord_system/
├── app.py                  # Streamlit entry point
├── db.py                   # Connection, CRUD helpers
├── logic.py                # Billing calculations (Strom, Gas, Wasser, BK, Heizung)
├── pdfgen.py               # ReportLab PDF generation
├── currencies.py           # EUR/CNY/USD/GBP symbol map
├── page_modules/           # One file per menu page
├── api/                    # FastAPI routers + Pydantic schemas
├── alembic/                # Schema migrations
└── scripts/                # DB dump, restore, sync, backup, Neon migration
```

---

## License

MIT
