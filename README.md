# Landlord Management System (Hausverwaltung)

A web-based property management application tailored for landlords in Germany. Built with Python and Streamlit, it covers the full rental lifecycle — from managing properties and tenants to generating legally-relevant documents like Nebenkostenabrechnungen and Mahnungen.

---

## Screenshots

| Dashboard | Properties |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Properties](docs/screenshots/properties.png) |

| Contracts | Rent Tracking |
|---|---|
| ![Contracts](docs/screenshots/contracts.jpg) | ![Rent Tracking](docs/screenshots/rent_tracking.png) |

| Nebenkostenabrechnung | Mahnung Generator |
|---|---|
| ![Nebenkostenabrechnung](docs/screenshots/nebenkostenabrechnung.png) | ![Mahnung Generator](docs/screenshots/mahnung_generator.jpg) |

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
- **Monthly cost summary** per flat: shows the current monthly equivalent (monthly entries + annual ÷ 12), with one-time costs noted separately
- Costs grouped by property and flat for easy overview

### Balance Sheet
- Monthly income vs. costs breakdown per property
- Income: rent payments recorded in the selected year
- Costs: flat costs prorated per month (annual ÷ 12, one-time in start month)
- Net per month color-coded (green = profit, red = loss)
- For the current year, only shows months up to the current month
- Annual totals: total income, total costs, annual net

### Nebenkostenabrechnung
- Freely select which utilities to include per Abrechnung: **Strom**, **Gas**, **Kaltwasser**, **Betriebskosten** — each is independent and optional
- Each utility has its **own billing period** from the provider, separate from the tenant's contract period
- Tenant's **effective period** is auto-detected as the intersection of the utility billing period and the tenant's contract dates — editable after auto-detection
- Changing a billing period automatically updates the effective period inputs
- **Correct proration**: `(total_flat_cost / bill_days) × eff_days / tenants` — accounts for partial occupancy within the billing period
- Strom, Gas, and Kaltwasser use day-based billing; Betriebskosten uses month-based billing with month/year selectors
- Auto-detects number of persons sharing the same flat via flat grouping (can be overridden)
- Generates a polished A4 letter-style PDF with:
  - Recipient address block and landlord name
  - Gender-aware salutation (Sehr geehrter Herr / Sehr geehrte Frau / Sehr geehrte/r)
  - Per-utility sections showing both the provider billing period and the tenant's effective period
  - Itemized step-by-step calculation tables (cost per day → tenant share → prepayment → Nachzahlung)
  - Color-coded total (red = Nachzahlung, green = Guthaben)
  - Landlord signature image
  - 7-day payment deadline for Nachzahlungen

### Mahnung Generator (Payment Reminder)
- Generate a formal payment reminder PDF for a tenant
- Gender-aware salutation
- Highlighted outstanding amount with due date
- Landlord signature embedded
- Ready to print or send digitally

---

## Tech Stack

| Layer       | Technology         |
|-------------|--------------------|
| UI          | Streamlit          |
| Database    | SQLite3            |
| PDF Engine  | ReportLab          |
| Language    | Python 3.10+       |

---

## Project Structure

```
landlord_system/
├── app.py              # Entry point — sidebar routing only
├── db.py               # Database initialization, CRUD helpers (insert, fetch, delete, execute)
├── logic.py            # Business logic: strom_calc, gas_calc, water_calc,
│                       #   betriebskosten_calc, tenant_ledger
├── pdfgen.py           # PDF generation: Nebenkostenabrechnung and Mahnung
├── requirements.txt    # Python dependencies
├── pages/              # One module per menu page
│   ├── dashboard.py
│   ├── properties.py
│   ├── apartments.py
│   ├── tenants.py
│   ├── tenant_ledger.py
│   ├── contracts.py
│   ├── rent_tracking.py
│   ├── flat_costs.py
│   ├── balance_sheet.py
│   ├── nebenkostenabrechnung.py
│   └── mahnung.py
├── data/
│   └── landlord.db     # SQLite database (auto-created on first run, git-ignored)
└── pdf/                # Output directory for generated PDFs (git-ignored)
```

---

## Database Schema

| Table        | Key Fields                                              |
|--------------|---------------------------------------------------------|
| `properties` | id, name, address                                       |
| `apartments` | id, property_id, name, flat                             |
| `tenants`    | id, name, email, gender                                 |
| `contracts`  | id, tenant_id, apartment_id, rent, start_date, end_date, terminated, kaution_amount, kaution_paid_date, kaution_returned_date, kaution_returned_amount |
| `payments`   | id, contract_id, amount, payment_date                   |
| `flat_costs` | id, apartment_id, cost_type, amount, frequency, valid_from, valid_to |

---

## Getting Started

### Prerequisites
- Python 3.10 or higher
- pip

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

# 4. Run the application
streamlit run app.py
```

The app will be available at `http://localhost:8501`.

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
