<p align="center">
  <img src="docs/favicon.svg" width="76" alt="Vermio" />
</p>

<h1 align="center">Vermio</h1>

<p align="center">Property management for German landlords — rent tracking, utility billing, Anlage&nbsp;V tax prep, PDF generation, and a data-aware AI assistant.</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Next.js-14-000000?logo=nextdotjs&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Assistant-Groq%20Llama%203.3-F55036" alt="Groq" />
  <img src="https://img.shields.io/badge/License-BSL%201.1-orange" alt="License" />
</p>

---

## What it does

Built to manage a handful of properties without commercial landlord software. Covers the full rental lifecycle — contracts, rent tracking, legally-formatted PDFs, year-end **Anlage V** tax prep, and a plain-language assistant that answers questions about your own data.

- **Nebenkostenabrechnung** — Strom, Gas, Wasser, Heizung, Betriebskosten with day-based, per-person proration. Each cost type takes meter readings *or* a direct total-cost figure, and can hold several billing periods (e.g. one provider bill per year) that are shown separately and summed into one statement. Person counts are WG-aware (co-tenant household vs. one contract per room); each Betriebskosten bill has its own editable *living period* from the contract; the outstanding amount can be offset against a still-held deposit. Generated PDFs carry the tenant's full address (street + postcode + city), the contract period, and a gender-aware salutation (Herr/Frau). Settings are saved as reusable billing profiles you can update in place.
- **Mahnung Generator** — formal payment reminder PDFs with gender-aware salutation, full property address, and signature
- **Kaution tracking** — log deductions, track open balance, mark returned, and offset against a Nebenkostenabrechnung
- **Balance Sheet** — monthly/annual P&L per property with per-flat breakdown, a current-month expected-net headline, and income-vs-target / net-trend charts
- **Anlage V (tax) helper** — per-property, per-year rental income and Werbungskosten totals in the categories the German Anlage V asks for, on a strict cash basis (§11 EStG). One-time AfA (building depreciation) setup, an annuity-mortgage split (only Schuldzinsen is deductible, not Tilgung), one-off expense entry with §82b multi-year distribution, and per-(property, year, field) manual overrides that win over computed values. Every figure is traceable to its source rows and exports as a fill-in PDF next to ELSTER. Auto-fills from live payment data for 2026+; 2025 has a manual-entry fallback.
- **Ask Vermio** — a read-only AI assistant you talk to in plain language. It answers by querying your own data through read-only tools (overdue rent, contracts, payments, tax report) *and* searching a German tenancy-law corpus, then composes a grounded answer that cites both (`[payments]`, `[BGB §551]`). Answers stream token-by-token with a live tool trace (which tool ran, with which arguments) and saved conversation threads.

Also: multi-currency (EUR/CNY/USD/GBP), co-tenants (Mitmieter), fixed-term and open-ended leases, meter readings, flat costs (Hausgeld, mortgage, Grundsteuer).

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | **Next.js 14** + TypeScript + Tailwind CSS + shadcn/ui + Recharts |
| API | **FastAPI** + Uvicorn (JWT auth) |
| Database | PostgreSQL 16 (Docker locally, Neon in cloud) |
| Migrations | Alembic |
| PDFs | ReportLab |
| Assistant | **Groq** (Llama 3.3 70B) — agentic tool-calling loop, SSE token streaming |
| Legal search | Hybrid RAG — sentence-transformers (e5) + Chroma + BM25, reranked, with citations |
| Container | Docker Compose |

The Next.js UI covers everything: dashboard with monthly charts, full CRUD for
properties/apartments/tenants/contracts, the multi-section Nebenkostenabrechnung
wizard (live calculation preview, per-period meter/total-cost billings, and
reusable, in-place-updatable billing profiles), Mahnung generation, balance-sheet
charts, per-meter reading history, co-tenant and Kaution management, payment
reminders, the **Anlage V** tax helper (per-property setup + yearly report with
PDF export), the **Ask Vermio** assistant, and SMTP/landlord settings.

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

The database schema is created automatically on first start (Alembic runs at API startup).

---

## Ask Vermio (AI assistant)

The `/ask` page is a read-only assistant that answers questions about your own
portfolio **and** German tenancy law, citing its sources. It runs an agentic
tool-calling loop (Groq — Llama 3.3 70B) over read-only data tools plus a hybrid
legal-RAG corpus.

- Set `GROQ_API_KEY` in `.env` — a free key from [console.groq.com](https://console.groq.com).
- The embedding + reranker models are **baked into the Docker image**, so nothing
  downloads at runtime; `make up` is all you need.
- For non-Docker dev, install the ML deps once: `pip install -r backend/requirements-rag.txt`.
- Without the key or those deps, the `/api/assistant/*` and `/api/rag/ask`
  endpoints return `503` — the rest of the app runs normally.

It is read-only in this phase: it reports and explains, and never mutates data.

---

## Local development (without Docker)

**Prerequisites:** Python 3.12+, Node.js 18+, Docker Desktop (for the DB container)

```bash
cp .env.example .env
./setup.sh                        # creates venv, starts landlord-pg container, runs migrations
source venv/bin/activate
honcho start                      # starts api + frontend together
```

For the Next.js frontend in dev mode:
```bash
cd frontend
npm install --legacy-peer-deps
npm run dev                       # http://localhost:3000
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local`.

---

## Tests

The backend calculation logic has a `pytest` suite (pure functions — no database
required):

```bash
pip install -r backend/requirements-dev.txt
make test            # or: cd backend && pytest
```

Covers the Nebenkostenabrechnung proration (`logic.py`), the Anlage V tax math
(`tax_logic.py` — annuity interest/Tilgung split, AfA, §82b distribution),
currency formatting, the SQLite→PostgreSQL query translation (`db._adapt`), and
the auth startup guard.

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
├── docker-compose.yml          # db + api + frontend
├── backend/                    # all Python (FastAPI + shared core)
│   ├── Dockerfile              # Python image (api)
│   ├── api/                    # FastAPI routers + Pydantic schemas
│   │   ├── routers/            # properties, tenants, contracts, payments, dashboard,
│   │   │                       # flat-costs, meters, kaution, billing-profiles,
│   │   │                       # co-tenants, reports, tax, assistant, rag, config
│   │   └── schemas/
│   ├── assistant/              # "Ask Vermio" agent: tool-calling loop, guardrails,
│   │                           #   tools, thread persistence, streaming
│   ├── rag/                    # Legal hybrid-RAG pipeline + corpus + index builder
│   ├── balance_compute.py      # balance-sheet computations (used by reports)
│   ├── db.py                   # DB connection + CRUD helpers
│   ├── logic.py                # Nebenkosten billing calculations
│   ├── tax_logic.py            # Anlage V tax math (annuity split, AfA, proration)
│   ├── pdfgen.py               # ReportLab PDF generation
│   ├── currencies.py           # EUR/CNY/USD/GBP symbol map
│   ├── auth.py                 # JWT + HTTP Basic auth + prod-config guard
│   ├── alembic/                # Schema migrations
│   ├── tests/                  # pytest suite (billing + tax logic, auth)
│   ├── requirements.txt
│   ├── requirements-rag.txt    # assistant/RAG ML deps (groq, sentence-transformers, chroma)
│   └── requirements-dev.txt    # test-only deps (pytest)
├── frontend/                   # Next.js app
│   ├── Dockerfile
│   ├── app/                    # App Router pages
│   └── components/             # Shared UI components
├── docs/                       # Landing page (GitHub Pages) + PRDs / TRDs
└── scripts/                    # Backup, sync, Neon migration
```

---

## License

[Business Source License 1.1](LICENSE). Source-available: you may read, modify,
and self-host it to manage your own rental properties, but offering it to third
parties as a hosted/commercial service is not permitted before the Change Date
(2030-07-06), after which it converts to Apache-2.0. For other arrangements,
contact the author.
