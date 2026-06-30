<p align="center">
  <img src="docs/logo-mark.svg" width="76" alt="Vermio" />
</p>

<h1 align="center">Vermio</h1>

<p align="center">Property management for German landlords — rent tracking, utility billing, and PDF generation.</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Next.js-14-000000?logo=nextdotjs&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License" />
</p>

---

## What it does

Built to manage a handful of properties without commercial landlord software. Covers the full rental lifecycle — contracts, rent tracking, and legally-formatted PDFs at year end.

- **Nebenkostenabrechnung** — Strom, Gas, Wasser, Heizung, Betriebskosten with day-based, per-person proration. Each cost type takes meter readings *or* a direct total-cost figure, and can hold several billing periods (e.g. one provider bill per year) that are shown separately and summed into one statement. Person counts are WG-aware (co-tenant household vs. one contract per room); each Betriebskosten bill has its own editable *living period* from the contract; the outstanding amount can be offset against a still-held deposit. Generated PDFs carry the tenant's full address (street + postcode + city), the contract period, and a gender-aware salutation (Herr/Frau). Settings are saved as reusable billing profiles you can update in place.
- **Mahnung Generator** — formal payment reminder PDFs with gender-aware salutation, full property address, and signature
- **Kaution tracking** — log deductions, track open balance, mark returned, and offset against a Nebenkostenabrechnung
- **Balance Sheet** — monthly/annual P&L per property with per-flat breakdown, a current-month expected-net headline, and income-vs-target / net-trend charts

Also: multi-currency (EUR/CNY/USD/GBP), co-tenants (Mitmieter), fixed-term and open-ended leases, meter readings, flat costs (Hausgeld, mortgage, Grundsteuer).

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | **Next.js 14** + TypeScript + Tailwind CSS + shadcn/ui + Recharts |
| API | **FastAPI** + Uvicorn (JWT auth) |
| Legacy UI | Streamlit (kept in parallel; the Next.js UI now has full feature parity) |
| Database | PostgreSQL 16 (Docker locally, Neon in cloud) |
| Migrations | Alembic |
| PDFs | ReportLab |
| Container | Docker Compose |

The Next.js UI covers everything: dashboard with monthly charts, full CRUD for
properties/apartments/tenants/contracts, the multi-section Nebenkostenabrechnung
wizard (live calculation preview, per-period meter/total-cost billings, and
reusable, in-place-updatable billing profiles), Mahnung generation, balance-sheet
charts, per-meter reading history, co-tenant and Kaution management, payment
reminders, and SMTP/landlord settings.

---

## Quick start (Docker)

```bash
git clone https://github.com/slgao/landlord_system.git
cd landlord_system
cp .env.example .env   # edit POSTGRES_PASSWORD if desired
make up                # build and start all containers
```

`make down` stops everything. Run `make` on its own to see all targets
(`logs`, `ps`, `restart`, `migrate`, `seed`, `clean`).

| Service | URL |
|---|---|
| **Next.js UI** | http://localhost:3000 |
| FastAPI | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Streamlit (legacy) | http://localhost:8501 |

The database schema is created automatically on first start (Alembic runs at API startup).

---

## Local development (without Docker)

**Prerequisites:** Python 3.12+, Node.js 18+, Docker Desktop (for the DB container)

```bash
cp .env.example .env
./setup.sh                        # creates venv, starts landlord-pg container, runs migrations
source venv/bin/activate
honcho start                      # starts api + streamlit together
```

For the Next.js frontend in dev mode:
```bash
cd frontend
npm install --legacy-peer-deps
npm run dev                       # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

---

## Auth

Protected by a bcrypt-hashed password. Set `APP_PASSWORD_HASH` in `.env`:

```bash
python -c 'import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt()).decode())'
```

Add the output to `.env` as `APP_PASSWORD_HASH=<hash>`. Leave unset for open access (local dev).

The Next.js frontend authenticates with a JWT Bearer token (7-day expiry). Set `JWT_SECRET` in `.env` to a random 32+ character string for production.

---

## Cloud database (Neon)

To share data across machines, point the app at a [Neon](https://neon.tech) PostgreSQL instance:

```bash
# One-time migration from local Docker to Neon
./scripts/migrate_to_neon.sh "postgresql://user:pass@host/neondb?sslmode=require"

# Sync local Docker from Neon (on any machine that drifted)
./scripts/sync_local_from_neon.sh
```

Update `DATABASE_URL` in `.env`. Alembic runs automatically on startup.

---

## Backups

`scripts/backup.sh` dumps Neon to gzip and retains 30 days. Set up with cron:

```bash
(crontab -l 2>/dev/null; echo "CRON_TZ=Europe/Berlin"; echo "0 22 * * * $PWD/scripts/backup.sh >> $HOME/landlord_backups/backup.log 2>&1") | crontab -
```

---

## Project layout

```
landlord_system/
├── Makefile                    # container orchestration (make up / down / …)
├── docker-compose.yml          # db + api + frontend + streamlit
├── backend/                    # all Python (FastAPI + Streamlit + shared core)
│   ├── Dockerfile              # Python image (api + streamlit)
│   ├── api/                    # FastAPI routers + Pydantic schemas
│   │   ├── routers/            # properties, tenants, contracts, payments,
│   │   │                       # dashboard, flat-costs, meters, config, reports
│   │   └── schemas/
│   ├── page_modules/           # Streamlit page modules (legacy)
│   ├── app.py                  # Streamlit entry point
│   ├── db.py                   # DB connection + CRUD helpers
│   ├── logic.py                # Billing calculations
│   ├── pdfgen.py               # ReportLab PDF generation
│   ├── currencies.py           # EUR/CNY/USD/GBP symbol map
│   ├── auth.py                 # JWT + HTTP Basic auth
│   ├── alembic/                # Schema migrations
│   └── requirements.txt
├── frontend/                   # Next.js app
│   ├── Dockerfile
│   ├── app/                    # App Router pages
│   └── components/             # Shared UI components
└── scripts/                    # Backup, sync, Neon migration
```

---

## License

MIT
