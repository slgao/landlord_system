# Landlord Management System (Hausverwaltung)

A web-based property management application tailored for landlords in Germany. Built with Python and Streamlit, it covers the full rental lifecycle — from managing properties and tenants to generating legally-relevant documents like Nebenkostenabrechnungen and Mahnungen.

---

## Screenshots

| Dashboard | Properties |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Properties](docs/screenshots/properties.png) |

| Apartments | Contracts |
|---|---|
| ![Apartments](docs/screenshots/apartments.png) | ![Contracts](docs/screenshots/contracts.png) |

| Rent Tracking | Flat Costs |
|---|---|
| ![Rent Tracking](docs/screenshots/rent_tracking.png) | ![Flat Costs](docs/screenshots/flat_costs.png) |

| Balance Sheet | Nebenkostenabrechnung |
|---|---|
| ![Balance Sheet](docs/screenshots/balance_sheet.png) | ![Nebenkostenabrechnung](docs/screenshots/nebenkostenabrechnung.png) |

| Mahnung Generator | |
|---|---|
| ![Mahnung Generator](docs/screenshots/mahnung_generator.png) | |

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
- **Heizkostenverteiler**: register heat cost allocator meters per apartment with serial number, description, unit label (e.g. "Einheiten"), and ISTA conversion factor (Einheiten → kWh)
- **Gaszähler**: register gas meters per apartment with serial number, Z-Zahl (Zustandszahl) and Brennwert from the NBB bill; Umrechnungsfaktor (m³ → kWh) is computed automatically as Z-Zahl × Brennwert

### Tenants
- Register tenants with name, email, and gender
- Edit tenant information and assigned apartment
- View tenants alongside their assigned apartment (via contract)
- Delete tenants from the system

### Contracts
- Create rental contracts linking a tenant to an apartment
- Set monthly rent amount
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
- **Kaution (deposit) tracking**: record deposit amount, date received, date and amount returned
- **Co-Tenants**: add additional occupants per contract with name, gender, and email
  - Toggle **In contract (Mitmieter)** for each person — those marked appear in the address block and salutation of all generated PDFs; others are stored for reference only
  - Person count for Nebenkostenabrechnung is auto-derived from primary tenant + all co-tenants

### Rent Tracking
- Monthly overview at the top: all payments across all properties for a selected month
- Record individual rent payments against a contract
- Supports partial and custom payment amounts
- Edit and delete existing payments

### Tenant Ledger
- View full payment history for any tenant
- Displays amount and date for each recorded payment
- Shows total amount paid

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

### Nebenkostenabrechnung
- Freely select which utilities to include per Abrechnung: **Strom**, **Gas**, **Kaltwasser**, **Betriebskosten**, **Heizkosten** — each is independent and optional
- **Multi-contract tenant support**: contract selector appears for tenants with multiple apartments; address auto-resolved from selected contract's property
- Each utility has its **own billing period** from the provider, separate from the tenant's contract period
- Tenant's **effective period** is auto-detected as the intersection of the utility billing period and the tenant's contract dates — editable after auto-detection
- **Gas Umrechnungsfaktor** is auto-filled from the registered Gaszähler (Z-Zahl × Brennwert)
- **Correct proration**: `(total_flat_cost / bill_days) × eff_days / tenants` — accounts for partial occupancy within the billing period
- Strom, Gas, and Kaltwasser use day-based billing; Betriebskosten uses month-based billing with month/year selectors
- Person count auto-derived from primary tenant + co-tenants (can be overridden)
- **Heizkostenverteiler (Heizkosten)**: enter meter start/end readings in ISTA units per Heizkörper; conversion factor (Einheiten → kWh) is taken from the meter registration
- Save and reload billing profiles to avoid re-entering data each year
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
- Landlord signature embedded

---

## Tech Stack

| Layer          | Technology               |
|----------------|--------------------------|
| UI             | Streamlit                |
| Database       | PostgreSQL 16 (Docker)   |
| DB Driver      | psycopg2                 |
| Migrations     | Alembic                  |
| PDF Engine     | ReportLab                |
| Language       | Python 3.10+             |

---

## Project Structure

```
landlord_system/
├── app.py                      # Entry point — sidebar routing only
├── db.py                       # PostgreSQL connection, CRUD helpers (insert, fetch, execute)
├── logic.py                    # Business logic: strom_calc, gas_calc, water_calc,
│                               #   betriebskosten_calc, heizung_calc_detail
├── pdfgen.py                   # PDF generation: Nebenkostenabrechnung and Mahnung
├── requirements.txt            # Python dependencies
├── .env                        # Database connection string (git-ignored, see Setup)
├── alembic.ini                 # Alembic configuration
├── alembic/
│   └── versions/               # Schema migration files
├── page_modules/               # One module per menu page
│   ├── dashboard.py
│   ├── properties.py
│   ├── apartments.py           # Heizkostenverteiler + Gaszähler meter management
│   ├── tenants.py
│   ├── tenant_ledger.py
│   ├── contracts.py            # Co-tenant management
│   ├── rent_tracking.py
│   ├── flat_costs.py
│   ├── balance_sheet.py
│   ├── nebenkostenabrechnung.py
│   ├── payment_reminders.py
│   └── mahnung.py
├── utils/
│   └── migrate_sqlite_to_pg.py # One-shot data migration script (SQLite → PostgreSQL)
└── pdf/                        # Output directory for generated PDFs (git-ignored)
```

---

## Database Schema

| Table              | Key Fields                                                                 |
|--------------------|----------------------------------------------------------------------------|
| `properties`       | id, name, address                                                          |
| `apartments`       | id, property_id, name, flat                                                |
| `tenants`          | id, name, email, gender                                                    |
| `contracts`        | id, tenant_id, apartment_id, rent, start_date, end_date, terminated, kaution_* |
| `payments`         | id, contract_id, amount, payment_date                                      |
| `flat_costs`       | id, apartment_id, cost_type, amount, frequency, valid_from, valid_to       |
| `heizung_meters`   | id, apartment_id, serial_number, description, unit_label, conversion_factor |
| `gas_meters`       | id, apartment_id, serial_number, description, z_zahl, brennwert            |
| `co_tenants`       | id, contract_id, name, gender, email, in_contract                         |
| `billing_profiles` | id, tenant_id, label, created_date, data                                   |
| `config`           | key, value                                                                 |

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

# 7. Run the application
streamlit run app.py
```

The app will be available at `http://localhost:8501`.

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
3. **Register Tenants** (with gender) → Tenants menu
4. **Create a Contract** linking tenant ↔ apartment with rent and dates → Contracts menu
5. **Record monthly Rent Payments** → Rent Tracking menu
6. **Review payment history** per tenant → Tenant Ledger menu
7. **Track Flat Costs** (Hausgeld, Mortgage, etc.) → Flat Costs menu
8. **Generate Nebenkostenabrechnung** at end of billing period → Nebenkostenabrechnung menu
9. **Send a Mahnung** if a tenant has outstanding payments → Mahnung Generator menu

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

## License

MIT
