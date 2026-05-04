# Landlord Management System (Hausverwaltung)

A web-based property management application tailored for landlords in Germany. Built with Python and Streamlit, it covers the full rental lifecycle — from managing properties and tenants to generating legally-relevant documents like Nebenkostenabrechnungen and Mahnungen.

---

## Screenshots

| Dashboard | Properties |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Properties](docs/screenshots/properties.png) |

| Tenants | Apartments |
|---|---|
| ![Tenants](docs/screenshots/tenants.png) | ![Apartments](docs/screenshots/apartments.png) |

| Contracts | Rent Tracking |
|---|---|
| ![Contracts](docs/screenshots/contracts.png) | ![Rent Tracking](docs/screenshots/rent_tracking.png) |

| Flat Costs | Balance Sheet |
|---|---|
| ![Flat Costs](docs/screenshots/flat_costs.png) | ![Balance Sheet](docs/screenshots/balance_sheet.png) |

| Meter Readings | Nebenkostenabrechnung |
|---|---|
| ![Meter Readings](docs/screenshots/meter_readings.png) | ![Nebenkostenabrechnung](docs/screenshots/nebenkostenabrechnung.png) |

| Mahnung Generator | Payment Reminders |
|---|---|
| ![Mahnung Generator](docs/screenshots/mahnung_generator.png) | ![Payment Reminders](docs/screenshots/payment_reminders.png) |

---

## Features

### Dashboard
- At-a-glance metrics: total properties, apartments, tenants, and contracts
- Automatic alerts for contracts expiring within the next 90 days
- Highlights already-expired contracts in red
- Terminated (moved-out) contracts are excluded from alerts

### Properties
- Add properties with name and address
- View all properties in a table
- Delete properties by selection

### Apartments
- Link apartments to a specific property
- Support for individual units and shared flat rooms (WG-Zimmer)
- **Flat grouping**: assign rooms to a named flat (e.g. "Wohnung 1") to group WG rooms together
- Edit existing apartments: room name and flat label
- Table shows property name alongside each apartment
- **Meter scope** — each registered meter carries a scope tag set at registration time:
  - **Room only** — belongs exclusively to this room (e.g. Heizkostenverteiler); not visible from sibling rooms in the same WG flat
  - **Shared (whole flat)** — shared by all rooms in the WG flat; visible from any room with the same flat label
- **Heizkostenverteiler**: register heat cost allocator meters per apartment with serial number, description, unit label (e.g. "Einheiten"), ISTA conversion factor (Einheiten → kWh), and scope (defaults to *Room only*)
- **Gaszähler**: register gas meters per apartment with serial number, Z-Zahl (Zustandszahl) and Brennwert from the NBB bill; Umrechnungsfaktor (m³ → kWh) is computed automatically as Z-Zahl × Brennwert; scope defaults to *Shared*
- **Stromzähler**: register electricity meters per apartment with serial number and description — serial is shown in the Nebenkostenabrechnung billing; scope defaults to *Shared*
- **Wasserzähler**: register cold water (Kaltwasser) and hot water (Warmwasser) meters per apartment with serial number and description — supports multiple meters per apartment; scope defaults to *Shared*

### Tenants
- Register tenants with name, email, and gender
- Edit tenant information and assigned apartment
- View tenants alongside their assigned apartment (via contract)
- Delete tenants from the system

### Contracts
- Create rental contracts linking a tenant to an apartment
- Set monthly rent amount with **currency selection** (EUR €, CNY ¥, USD $, GBP £) — each contract has its own currency
- Support for open-ended and fixed-term (befristet) contracts
- Overlap detection: warns if the apartment is already occupied in the selected period (excludes terminated contracts)
- Edit existing contracts: apartment, rent, start/end dates
- **Contract status tracking** — each contract is labelled:
  - **Active** — running, no end date or future end date
  - **Expiring soon** — end date within 90 days (orange)
  - **Expired** — end date in the past, not yet resolved (red, needs attention)
  - **Moved out** — explicitly closed (gray, historical)
- **Terminate Contract**: sets the move-out date and marks the contract as closed
- **Handle Expired Contracts**: single expander for all unresolved expired contracts with a radio choice:
  - *Close — tenant has moved out* → marks as terminated, removes from alerts
  - *Reopen — tenant is still living there* → clears end date, restores to active
- **Kaution (deposit) tracking**: record deposit amount and date received, log partial deductions (NK Nachzahlung verrechnet, Schaden, Reinigung, Mietrückstand, Sonstiges) with free-text reason, and mark the remaining balance returned
  - Kaution has its **own currency selector** (independent of the rent currency) — useful when a deposit is paid in a different currency (e.g. CNY)
  - Per-contract overview shows received / deducted / **open balance** / returned, all formatted with the correct currency symbol
  - Returned amount auto-defaults to the open balance and is blocked if it exceeds it
  - Once marked returned, balance switches to *settled* and further deductions are blocked until the return record is cleared
- **Co-Tenants**: add additional occupants per contract with name, gender, and email
  - Toggle **In contract (Mitmieter)** for each person — those marked appear in the address block and salutation of all generated PDFs; others are stored for reference only
  - Person count for Nebenkostenabrechnung is auto-derived from primary tenant + all co-tenants

### Rent Tracking
- Monthly overview at the top: all payments across all properties for a selected month
- Record individual rent payments against a contract
- **Per-payment currency**: each payment can be recorded in EUR €, CNY ¥, USD $, or GBP £ — defaults to the contract's currency but can be overridden per payment
- Monthly total and per-contract total are shown **grouped by currency** when mixed currencies are present
- Supports partial and custom payment amounts
- Edit and delete existing payments (currency is editable too)

### Tenant Ledger
- View full payment history for any tenant
- Displays amount (with currency symbol) and date for each recorded payment
- Total is shown grouped by currency when a tenant has paid in multiple currencies

### Flat Costs
- Record recurring and one-time costs per apartment (Hausgeld, Mortgage, Grundsteuer, Strom Vorauszahlung, Internet, custom)
- Set frequency: monthly, annual, or one-time
- Set validity period (valid from / valid to)
- Edit and delete existing cost entries
- **Grand summary table**: all flats listed with their active monthly equivalent, annual total, and one-time count
- **Grand total metrics**: total monthly and annual costs across all flats at a glance
- **Per-flat detail expanders**: itemized list with active/expired status, monthly equivalent per entry, and flat-level totals

### Balance Sheet
- **Current monthly snapshot**: metric cards per property + grand total across all properties showing expected rent minus costs for the current month
- **Annual view** (year selector): per-property table with Expected rent, Actual received, Variance, Costs, Expected net, Actual net — all color-coded (green = profit/surplus, red = loss/shortfall)
- For the current year, only shows months up to the current month
- **Annual summary metrics**: expected rent, actual received (with delta vs expected), total costs, and net actual (with expected net delta)
- **Per-flat breakdown expander**: current active contracts per apartment showing tenant name, rent/month, received for the year, costs/month, net/month, net/year, and YTD collection rate %
- **WG auto-detection**: flats sharing the same label are grouped; monthly payment pivot table per tenant is shown for WG tenancies
- **Performance insights & suggestions**: auto-generated per-flat observations — vacancy alerts, negative-net warnings, arrears detection (with Mahnung recommendation), and thin-margin notices

### Meter Readings (Zählerstände)
- Track meter readings over time, independently of any Nebenkostenabrechnung run
- Covers all meter types: Strom, Gas, Heizung, Kaltwasser, Warmwasser
- Select apartment → all meters visible to that apartment are shown, respecting **meter scope**:
  - *Room only* meters appear only for their own room
  - *Shared* meters appear for every room in the same WG flat
- **Add readings** with date, value, and an optional note
- **Consumption analysis per meter**: table showing each reading, Δ consumption since previous, days elapsed, and average daily consumption
- **Summary metrics**: total consumption since first reading, days covered, overall average/day
- **Line chart** of readings over time for each meter
- Delete individual readings

### Nebenkostenabrechnung
- **Landlord signature**: upload an image (PNG/JPG) *or* draw directly on an HTML5 canvas whiteboard — supports undo step-by-step and clear; saved signature is auto-cropped to content and shown in a live-refreshing preview
- Freely select which utilities to include per Abrechnung: **Strom**, **Gas**, **Kaltwasser**, **Warmwasser**, **Betriebskosten**, **Heizkosten** — each is independent and optional
- **WG meter scope awareness**: meter lookup respects the scope tag — *Room only* meters (e.g. individual Heizkostenverteiler) are shown only for their room; *Shared* meters (e.g. a single Stromzähler for the whole flat) are shown for all rooms in the WG
- **Multi-contract tenant support**: contract selector appears for tenants with multiple apartments; address auto-resolved from selected contract's property
- Each utility has its **own billing period** from the provider, separate from the tenant's contract period
- Tenant's **effective period** is auto-detected as the intersection of the utility billing period and the tenant's contract dates — editable after auto-detection
- **Meter serial numbers shown in billing**: registered Stromzähler and Kaltwasserzähler Zählernummer appear as an info banner in the respective billing section
- **Gas Umrechnungsfaktor** is auto-filled from the registered Gaszähler (Z-Zahl × Brennwert)
- **Warmwasser (hot water) billing**: supports one or multiple Warmwasserzähler per apartment; prices are broken down into Frischwasser, Abwasser, and Heizenergie (€/m³) — useful when warm water heating is billed separately from Heizkosten
- **Correct proration**: `(total_flat_cost / bill_days) × eff_days / tenants` — accounts for partial occupancy within the billing period
- Strom, Gas, Kaltwasser, and Warmwasser use day-based billing; Betriebskosten uses month-based billing with month/year selectors
- Person count auto-derived from primary tenant + co-tenants (can be overridden)
- **Heizkostenverteiler (Heizkosten)**: enter meter start/end readings in ISTA units per Heizkörper; conversion factor (Einheiten → kWh) is taken from the meter registration
- **Billing profiles** save and reload all entered values to avoid re-entering data each year; profiles are linked to the specific contract they were saved for — loading a profile automatically selects the corresponding contract
- Generates a polished A4 letter-style PDF with:
  - Recipient address block listing primary tenant and all Mitmieter (in-contract co-tenants only)
  - Gender-aware salutation for one or multiple named tenants; falls back to "Sehr geehrte Damen und Herren" for 3+
  - Header banner shows billing periods for all included utilities
  - Per-utility sections showing both the provider billing period and the tenant's effective period
  - Itemized step-by-step calculation tables
  - Color-coded total (red = Nachzahlung, green = Guthaben)
  - Landlord signature image and 7-day payment deadline for Nachzahlungen

### Mahnung Generator (Payment Reminder)
- Generate a formal payment reminder PDF for a tenant
- **Multi-contract support**: contract selector appears for tenants with multiple apartments
- All Mitmieter (in-contract co-tenants) appear in the address block and salutation
- Gender-aware salutation for one or multiple named tenants
- Highlighted outstanding amount with due date
- Landlord signature embedded (shared with Nebenkostenabrechnung — upload or draw once, used everywhere)

---

## Tech Stack

| Layer          | Technology               |
|----------------|--------------------------|
| UI (admin)     | Streamlit                |
| API            | FastAPI + Uvicorn        |
| Database       | PostgreSQL 16 (Docker)   |
| DB Driver      | psycopg2                 |
| Migrations     | Alembic                  |
| PDF Engine     | ReportLab                |
| Language       | Python 3.10+             |

---

## Project Structure

```
landlord_system/
├── app.py                      # Streamlit entry point — sidebar routing
├── db.py                       # PostgreSQL connection, CRUD helpers (insert, fetch, execute)
├── logic.py                    # Business logic: strom_calc, gas_calc, water_calc,
│                               #   warmwasser_calc_detail, betriebskosten_calc, heizung_calc_detail
├── currencies.py               # Supported currencies (EUR/CNY/USD/GBP), symbol map, fmt() helper
├── pdfgen.py                   # PDF generation: Nebenkostenabrechnung and Mahnung
├── requirements.txt            # Python dependencies
├── Procfile                    # Run both services with `honcho start`
├── .env                        # Database connection string (git-ignored, see Setup)
├── alembic.ini                 # Alembic configuration
├── alembic/
│   └── versions/               # Schema migration files
├── api/                        # FastAPI backend
│   ├── main.py                 # App factory, CORS, router registration
│   ├── routers/
│   │   ├── properties.py       # CRUD /api/properties
│   │   ├── apartments.py       # GET  /api/apartments
│   │   ├── tenants.py          # CRUD /api/tenants
│   │   ├── contracts.py        # GET  /api/contracts
│   │   └── payments.py         # CRUD /api/payments
│   └── schemas/                # Pydantic request/response models
│       ├── property.py
│       ├── apartment.py
│       ├── tenant.py
│       ├── contract.py
│       └── payment.py
├── page_modules/               # Streamlit — one module per menu page
│   ├── dashboard.py
│   ├── properties.py
│   ├── apartments.py           # Heizkostenverteiler + Gaszähler + Stromzähler + Wasserzähler
│   ├── tenants.py
│   ├── tenant_ledger.py
│   ├── contracts.py            # Co-tenant management
│   ├── rent_tracking.py
│   ├── flat_costs.py
│   ├── meter_readings.py       # Time-series meter readings + consumption analysis
│   ├── balance_sheet.py
│   ├── nebenkostenabrechnung.py
│   ├── payment_reminders.py
│   └── mahnung.py
├── utils/
│   ├── migrate_sqlite_to_pg.py # One-shot data migration script (SQLite → PostgreSQL)
│   └── backup.sh               # Daily backup script
└── pdf/                        # Output directory for generated PDFs (git-ignored)
```

---

## Database Schema

| Table              | Key Fields                                                                 |
|--------------------|----------------------------------------------------------------------------|
| `properties`       | id, name, address                                                          |
| `apartments`       | id, property_id, name, flat                                                |
| `tenants`          | id, name, email, gender                                                    |
| `contracts`        | id, tenant_id, apartment_id, rent, start_date, end_date, terminated, kaution_*, **currency**, **kaution_currency** |
| `kaution_deductions` | id, contract_id, date, amount, category, reason, reference_type, reference_id |
| `payments`         | id, contract_id, amount, payment_date, **currency**                        |
| `flat_costs`       | id, apartment_id, cost_type, amount, frequency, valid_from, valid_to       |
| `heizung_meters`   | id, apartment_id, serial_number, description, unit_label, conversion_factor, **scope** |
| `gas_meters`       | id, apartment_id, serial_number, description, z_zahl, brennwert, **scope** |
| `strom_meters`     | id, apartment_id, serial_number, description, **scope**                    |
| `wasser_meters`    | id, apartment_id, serial_number, description, type ('kalt'\|'warm'), **scope** |
| `meter_readings`   | id, meter_type, meter_id, reading_date, reading, note                      |
| `co_tenants`       | id, contract_id, name, gender, email, in_contract                         |
| `billing_profiles` | id, tenant_id, label, created_date, data (JSON incl. contract_id)          |
| `config`           | key, value                                                                 |

> **currency** — one of `EUR`, `CNY`, `USD`, `GBP`; defaults to `EUR` on existing rows.  
> **scope** — `room` (this room only) or `shared` (whole WG flat); default varies by meter type.

---

## Getting Started

### Prerequisites
- Python 3.10 or higher
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for PostgreSQL)

### Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd landlord_system

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the PostgreSQL database (first time only)
docker run -d \
  --name landlord-pg \
  -e POSTGRES_USER=landlord \
  -e POSTGRES_PASSWORD=secret \
  -e POSTGRES_DB=landlord_dev \
  -p 5432:5432 \
  --restart unless-stopped \
  postgres:16

# 5. Create .env with the database connection string
echo "DATABASE_URL=postgresql://landlord:secret@localhost:5432/landlord_dev" > .env

# 6. Initialise the database schema
python3 -c "from db import init_db; init_db()"

# 7. Run both services (Streamlit + FastAPI)
honcho start
```

| Service | URL |
|---|---|
| Streamlit admin UI | `http://localhost:8501` |
| FastAPI backend | `http://localhost:8000` |
| API docs (Swagger) | `http://localhost:8000/docs` |
| API docs (ReDoc) | `http://localhost:8000/redoc` |

Or run them separately in two terminals:
```bash
# Terminal 1 — API
uvicorn api.main:app --reload --port 8000

# Terminal 2 — Streamlit
streamlit run app.py
```

### Daily Use

**You do not need to run `docker run` again.** The container was created with `--restart unless-stopped`, so it starts automatically whenever Docker Desktop is open.

Your daily workflow is simply:

1. Open **Docker Desktop** (the container starts automatically)
2. Activate your virtual environment: `source venv/bin/activate`
3. Run the app: `streamlit run app.py`

---

## Inspecting the Database

### Option 1 — psql CLI (no extra install needed)

```bash
docker exec -it landlord-pg psql -U landlord -d landlord_dev
```

Useful psql commands:
```sql
\dt                        -- list all tables
\d contracts               -- describe a table's columns
SELECT * FROM properties;  -- query any table
SELECT COUNT(*) FROM payments;
\q                         -- quit
```

### Option 2 — GUI client

Connect any database GUI to:

| Setting  | Value        |
|----------|--------------|
| Host     | `localhost`  |
| Port     | `5432`       |
| User     | `landlord`   |
| Password | `secret`     |
| Database | `landlord_dev` |

Recommended free GUI tools:
- **[TablePlus](https://tableplus.com/)** — native Mac app, clean UI (free tier available)
- **[DBeaver](https://dbeaver.io/)** — cross-platform, fully free
- **[pgAdmin](https://www.pgadmin.org/)** — official PostgreSQL tool, web-based

---

## Schema Migrations

Database schema changes are managed with [Alembic](https://alembic.sqlalchemy.org/).

```bash
# Check current migration status
alembic current

# Apply any pending migrations
alembic upgrade head

# Create a new migration after a schema change
alembic revision -m "add_phone_to_tenants"
# Edit the generated file in alembic/versions/, then:
alembic upgrade head
```

---

## Usage Guide

### Typical Workflow

1. **Add a Property** → Properties menu
2. **Add Apartments** to the property → Apartments menu
3. **Register meters** (Heizkostenverteiler, Gaszähler, Stromzähler, Wasserzähler) per apartment → Apartments menu
4. **Register Tenants** (with gender) → Tenants menu
5. **Create a Contract** linking tenant ↔ apartment with rent and dates → Contracts menu
6. **Record monthly Rent Payments** → Rent Tracking menu
7. **Track meter readings** throughout the year → Meter Readings menu
8. **Review payment history** per tenant → Tenant Ledger menu
9. **Track Flat Costs** (Hausgeld, Mortgage, etc.) → Flat Costs menu
10. **Generate Nebenkostenabrechnung** at end of billing period → Nebenkostenabrechnung menu
11. **Send a Mahnung** if a tenant has outstanding payments → Mahnung Generator menu

### Move-out / Move-in Flow

1. Go to **Contracts** → *Terminate Contract* → set move-out date (marks contract as "Moved out")
2. Create a new contract for the incoming tenant on the same apartment
3. The overlap check excludes terminated contracts, so the apartment is considered free

### Handling Expired Contracts

If a fixed-term contract's end date has passed without being explicitly terminated:

- The contract appears in red (**Expired**) in the contracts table and triggers a dashboard alert
- Go to **Contracts** → *Handle Expired Contracts*
- Choose the action:
  - **Close** — tenant has moved out → marks as terminated, removes from alerts
  - **Reopen** — tenant is still living there → clears the end date, restores to active

### Nebenkostenabrechnung Calculation Logic

Each utility is billed independently. The tenant's effective period is the intersection of the utility's billing period and the tenant's contract dates.

**Electricity (Strom), Gas, Cold Water (Kaltwasser):**
```
bill_days           = total days in provider billing period
eff_days            = days tenant lived in flat (within billing period)
cost_per_day        = total_flat_cost / bill_days
tenant_cost         = cost_per_day × eff_days / num_tenants
daily_prepayment    = (monthly_limit × 12) / 365 / num_tenants
period_prepayment   = daily_prepayment × eff_days
Nachzahlung         = tenant_cost − period_prepayment
```

**Warmwasser (Hot Water) — day-based, multiple meters summed:**
```
verbrauch_m3        = Σ (end − start) across all Warmwasserzähler
cost_per_m3         = frischwasser_€/m³ + abwasser_€/m³ + heizenergie_€/m³
cost_flat           = verbrauch_m3 × cost_per_m3
tenant_cost         = cost_flat × eff_days / bill_days / num_tenants
Nachzahlung         = tenant_cost − period_prepayment
```

**Betriebskosten (month-based):**
```
num_months          = total months in provider billing period
eff_months          = months tenant lived in flat (within billing period)
cost_per_tenant     = total_bk_cost / num_tenants
period_cost         = (cost_per_tenant / num_months) × eff_months
period_prepayment   = (monthly_limit / num_tenants) × eff_months
Nachzahlung (BK)    = period_cost − period_prepayment
```

**Total due = sum of all Nachzahlungen across selected utilities**

---

## Generated Documents

All PDFs are saved to the `pdf/` directory and can be downloaded directly from the Streamlit UI.

| Document                  | Filename pattern              |
|---------------------------|-------------------------------|
| Nebenkostenabrechnung     | `pdf/Abrechnung_<Tenant>.pdf` |
| Mahnung (Payment Reminder)| `pdf/Mahnung_<Tenant>.pdf`    |

---

## Database Backups

### Manual backup

```bash
# Create a compressed dump
docker exec landlord-pg pg_dump -U landlord landlord_dev | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Automated daily backup

A backup script is included at `~/landlord_backups/backup.sh`. It runs every night at 22:00 (Europe/Berlin) via cron, keeps the last 30 backups, and logs results.

**First-time setup:**

```bash
# 1. Create the backup directory
mkdir -p ~/landlord_backups

# 2. Copy the backup script
cp utils/backup.sh ~/landlord_backups/backup.sh
chmod +x ~/landlord_backups/backup.sh

# 3. Test it manually
~/landlord_backups/backup.sh

# 4. Schedule via cron (runs daily at 22:00 Europe/Berlin)
(crontab -l 2>/dev/null; echo "CRON_TZ=Europe/Berlin"; echo "0 22 * * * /Users/$(whoami)/landlord_backups/backup.sh >> /Users/$(whoami)/landlord_backups/backup.log 2>&1") | crontab -
```

**Check backup log:**

```bash
cat ~/landlord_backups/backup.log
```

### Restore from a backup

```bash
# List available backups
ls -lh ~/landlord_backups/landlord_*.sql.gz

# Restore (CAUTION: overwrites current data)
gunzip -c ~/landlord_backups/landlord_20260408_203842.sql.gz \
  | docker exec -i landlord-pg psql -U landlord -d landlord_dev
```

### Backup summary

| What | Detail |
|---|---|
| Backup location | `~/landlord_backups/landlord_YYYYMMDD_HHMMSS.sql.gz` |
| Schedule | Daily at 22:00 (Europe/Berlin) |
| Retention | Last 30 days |
| Log | `~/landlord_backups/backup.log` |

> **macOS note:** cron only runs while the Mac is awake. If reliability matters, schedule the backup for a time the Mac is normally on.

---

## REST API

The FastAPI backend runs on port 8000 and exposes the core data as a REST API — ready to be consumed by a future Next.js frontend or tenant portal.

Interactive docs are auto-generated at **`http://localhost:8000/docs`**.

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/properties/` | List all properties |
| POST | `/api/properties/` | Create a property |
| GET | `/api/properties/{id}` | Get a property |
| PUT | `/api/properties/{id}` | Update a property |
| DELETE | `/api/properties/{id}` | Delete a property |
| GET | `/api/apartments/` | List apartments (filter: `?property_id=`) |
| GET | `/api/apartments/{id}` | Get an apartment |
| GET | `/api/tenants/` | List all tenants |
| POST | `/api/tenants/` | Create a tenant |
| GET | `/api/tenants/{id}` | Get a tenant |
| PUT | `/api/tenants/{id}` | Update a tenant |
| DELETE | `/api/tenants/{id}` | Delete a tenant |
| GET | `/api/contracts/` | List contracts (filter: `?active_only=true`) |
| GET | `/api/contracts/{id}` | Get a contract |
| GET | `/api/contracts/tenant/{tenant_id}` | Contracts for a tenant |
| GET | `/api/payments/` | List payments (filter: `?contract_id=` or `?tenant_id=`) |
| POST | `/api/payments/` | Record a payment |
| DELETE | `/api/payments/{id}` | Delete a payment |
| GET | `/api/signature` | Get the current landlord signature PNG |
| POST | `/api/signature` | Save a new signature (base64 data URL body) |
| GET | `/api/signature-pad` | HTML5 canvas drawing pad (embedded as iframe in Streamlit) |

### Architecture

```
Streamlit (port 8501)  ←──── direct db.py calls (current)
                                       │
FastAPI   (port 8000)  ←──── same db.py + logic.py reused
                                       │
                              PostgreSQL (port 5432)
```

Both services share the same `db.py` layer and PostgreSQL database. The FastAPI layer is the foundation for a future Next.js tenant portal or mobile app.

---

## Roadmap

### Phase 1 — Multi-user & Authentication
- [ ] Add `landlord_id` column to all tables (Alembic migration)
- [ ] Add `landlords` table with hashed passwords
- [ ] Wrap Streamlit with `streamlit-authenticator` — login/logout per landlord
- [ ] Filter all queries by `landlord_id` so each landlord sees only their own data
- [ ] Admin page to create/manage landlord accounts

### Phase 2 — API Security
- [ ] JWT authentication on FastAPI endpoints (`/api/auth/login` → token)
- [ ] Protect all API routes with `Depends(get_current_user)`
- [ ] Rate limiting and request logging
- [ ] PostgreSQL Row-Level Security (RLS) — enforce data isolation at DB level

### Phase 3 — Tenant Portal (Next.js)
- [ ] Next.js frontend consuming the FastAPI backend
- [ ] Tenant login — view own contract, payment history, NK-Abrechnung PDFs
- [ ] Submit maintenance requests
- [ ] Receive and acknowledge Mahnungen digitally
- [ ] Mobile-responsive layout (Tailwind CSS + shadcn/ui)

### Phase 4 — Migrate Landlord UI from Streamlit to Next.js
> Streamlit is a great tool for internal dashboards but has limitations for a production SaaS:
> no real URL routing, no mobile-first layout, no real-time features, and auth is bolted on.
> Once the FastAPI backend is mature and a tenant portal exists in Next.js, the landlord
> admin dashboard should be migrated page-by-page to Next.js as well.
- [ ] Migrate Dashboard page to Next.js
- [ ] Migrate Properties / Apartments / Tenants / Contracts pages
- [ ] Migrate Rent Tracking and Balance Sheet
- [ ] Migrate Nebenkostenabrechnung and Mahnung Generator (PDF preview in browser)
- [ ] Retire Streamlit once all pages are migrated
- [ ] Full Keycloak or Supabase Auth (OIDC/OAuth2, Google login) replacing streamlit-authenticator

### Phase 5 — Automation & Integrations
- [ ] Email delivery — send NK-Abrechnung and Mahnung PDFs directly to tenants (Brevo / Postal)
- [ ] Automated rent reminder scheduler (Celery + Redis) — trigger Mahnung if payment overdue
- [ ] Bank integration via FinTS/HBCI (`python-fints`) — auto-import and reconcile payments
- [ ] SEPA direct debit via GoCardless — pull rent automatically from tenant accounts

### Phase 6 — Document & Contract Management
- [ ] E-signature for rental contracts (Documenso — open-source DocuSign alternative)
- [ ] Document storage per tenant/contract (MinIO or S3-compatible)
- [ ] Certified e-delivery tracking for NK-Abrechnungen (BGB 12-month deadline)

### Phase 7 — Reporting & Tax
- [ ] Anlage V export — structured annual income/cost summary for German tax return
- [ ] Depreciation (AfA) tracking per property
- [ ] Annual profit/loss report per property with downloadable PDF

### Phase 8 — Market Intelligence
- [ ] Market rent benchmarking — compare current rents to local listings
- [ ] Alert when a flat's rent is significantly below market rate
- [ ] Yield calculator per property (annual net / estimated property value)

### Phase 9 — Deployment
- [ ] Docker Compose for local dev (app + API + PostgreSQL + Redis in one command)
- [ ] Deploy to Hetzner VPS with Coolify (Git push → auto deploy)
- [ ] SSL via Let's Encrypt / Traefik reverse proxy
- [ ] CI/CD pipeline (GitHub Actions — run tests on every push)

---

## License

MIT
