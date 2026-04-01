# Landlord Management System (Hausverwaltung)

A web-based property management application tailored for landlords in Germany. Built with Python and Streamlit, it covers the full rental lifecycle — from managing properties and tenants to generating legally-relevant documents like Nebenkostenabrechnungen and Mahnungen.

---

## Features

### Dashboard
- At-a-glance metrics: total properties and tenants
- Automatic alerts for contracts expiring within the next 90 days
- Highlights already-expired contracts in red

### Properties
- Add properties with name and address
- View all properties in a table
- Delete properties by ID

### Apartments
- Link apartments to a specific property
- Support for individual units and shared flat rooms (WG-Zimmer)
- View and delete existing apartments

### Tenants
- Register tenants with name and email
- View tenants alongside their assigned apartment (via contract)
- Delete tenants from the system

### Contracts
- Create rental contracts linking a tenant to an apartment
- Set monthly rent amount
- Support for open-ended and fixed-term (befristet) contracts
- View all active contracts with start/end dates
- Terminate or delete contracts

### Rent Tracking
- Record individual rent payments against a contract
- Specify payment amount and date
- Supports partial and custom payment amounts

### Tenant Ledger
- View full payment history for any tenant
- Displays amount and date for each recorded payment

### Nebenkostenabrechnung (Utility Billing)
- Calculate electricity costs (Strom) per tenant based on:
  - Total flat cost
  - Number of tenants
  - Billing period (in days)
  - Monthly prepayment limit
- Calculate Betriebskosten per tenant based on:
  - Total operating costs
  - Number of tenants
  - Billing period (in months)
  - Monthly prepayment limit
- Automatically computes Nachzahlung (additional payment due)
- Generates a formatted PDF (A4) with itemized billing tables

### Mahnung Generator (Payment Reminder)
- Generate a formal payment reminder PDF for a tenant
- Includes tenant name and outstanding amount
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
├── app.py              # Main Streamlit app — UI layout and page routing
├── db.py               # Database initialization, CRUD helpers (insert, fetch, delete, execute)
├── logic.py            # Business logic: cost calculations (Strom, BK), tenant ledger
├── pdfgen.py           # PDF generation: Nebenkostenabrechnung and Mahnung
├── requirements.txt    # Python dependencies
├── data/
│   └── landlord.db     # SQLite database (auto-created on first run)
└── pdf/                # Output directory for generated PDFs
```

---

## Database Schema

| Table        | Key Fields                                              |
|--------------|---------------------------------------------------------|
| `properties` | id, name, address                                       |
| `apartments` | id, property_id, name                                   |
| `tenants`    | id, name, email                                         |
| `contracts`  | id, tenant_id, apartment_id, rent, start_date, end_date |
| `payments`   | id, contract_id, amount, payment_date                   |

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
3. **Register Tenants** → Tenants menu
4. **Create a Contract** linking tenant ↔ apartment with rent and dates → Contracts menu
5. **Record monthly Rent Payments** → Rent Tracking menu
6. **Review payment history** per tenant → Tenant Ledger menu
7. **Generate Nebenkostenabrechnung** at end of billing period → Nebenkostenabrechnung menu
8. **Send a Mahnung** if a tenant has outstanding payments → Mahnung Generator menu

### Nebenkostenabrechnung Calculation Logic

**Electricity (Strom):**
```
cost_per_tenant     = total_flat_cost / number_of_tenants
daily_limit         = (monthly_limit × 12) / 365 / tenants
period_limit        = daily_limit × billing_days
Nachzahlung (Strom) = cost_per_tenant − period_limit
```

**Betriebskosten:**
```
cost_per_tenant  = total_bk_cost / number_of_tenants
period_cost      = (cost_per_tenant / total_months) × billed_months
period_limit     = (monthly_limit / tenants) × billed_months
Nachzahlung (BK) = period_cost − period_limit
```

**Total due = Nachzahlung Strom + Nachzahlung BK**

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
