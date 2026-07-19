# PRD — Vermio Tax Module (Anlage V Helper)

**Status:** Phase-1 MVP implemented (2026-07-19) · **Author:** Shulin + Claude
**Deadline driver:** 2025 tax declaration due **2026-07-31** (self-filed via ELSTER)

---

## 1. Problem

Vermio tracks properties, contracts, rent payments, and recurring costs — but at tax
time all of it has to be manually re-aggregated into **Anlage V** (Einkünfte aus
Vermietung und Verpachtung), one form **per property**, per tax year. With 8
properties / 12 apartments that is hours of error-prone spreadsheet work, repeated
every year.

The module's job: for **any chosen tax year**, produce per-property income and
Werbungskosten totals in the categories Anlage V asks for, exportable as a
fill-in helper next to the ELSTER portal. It is a permanent yearly workflow, not
a 2025 one-off: 2025 is merely the one year that needs a manual-entry fallback
(no payment records exist for it); from tax year 2026 onward the report
auto-fills from live data, and each new year only requires reviewing one-off
expenses and pressing export.

## 2. Hard constraints found in the data audit (2026-07-19)

| Fact | Consequence |
|---|---|
| `payments` begins **2026-01-01** (67 rows, all 2026) | Tax year **2025 cannot be auto-filled** from payments. 2026 onward can be, fully. |
| `flat_costs` = recurring monthly definitions (`valid_from`/`valid_to`), types: Gas/Strom Vorauszahlung, Grundsteuer, Hausgeld, Internet, Miete, Mortgage, Rundfunk, Verwaltungsbetreuung | Recurring expenses can be expanded to per-year totals for any year ≥ 2021. **One-off expenses (repairs / Erhaltungsaufwand) have no home** in the schema. |
| `Mortgage` is one amount | Only the **interest** portion (Schuldzinsen) is deductible, not Tilgung. Needs a split or an interest-only entry. |
| No purchase data anywhere | **AfA** (building depreciation, typically the largest single deduction) cannot be computed; needs a one-time per-property setup. |
| Payments are one amount per contract | Kaltmiete vs. Nebenkosten-Umlage split (Anlage V reports them separately) is not recorded. Both are taxable income, so the *total* is correct; the split needs contract-level metadata. |
| `kaution_payments` exist | Deposits are **not income** — must be excluded from any income aggregation. |

## 3. Tax-domain rules the module must respect

- **Zufluss-/Abflussprinzip (§11 EStG):** cash basis. Income counts in the year it
  *arrived*, expenses in the year *paid* — not the period they cover. (The
  payment-reminders "cumulative balance" logic is period-based; the tax module must
  aggregate strictly by `payment_date` year.)
- **One Anlage V per property**, income/expenses per property (apartment-level data
  aggregates up via `apartments.property_id`).
- **Umlagen received are income; Nebenkosten paid are Werbungskosten.** No netting.
- **Kaution:** never income on receipt; only if kept to cover claims (rare — out of
  MVP, manual override note is enough).
- **AfA:** linear 2 % (building completed 1925–2022), 2.5 % (pre-1925), 3 %
  (completed ≥ 2023), applied to the *building* share of purchase price (land share
  not depreciable). First/last year pro-rata by month.
- **Vacancy:** expenses still deductible while intent to rent exists — module just
  reports what was paid; no special handling needed beyond not requiring a contract.
- Exact Anlage V line numbers shift between form years → the module maps to **stable
  category names**, with the form-line reference shown as editable text, verified
  against the current-year form at filing time.

## 4. Users & jobs

Single user (owner-operator landlord). Jobs:
1. *(now, once)* "Give me my 2025 numbers per property so I can type them into ELSTER before July 31."
2. *(every year after)* "One click → per-property Anlage V numbers for last year, mostly auto-filled from payments/costs."
3. *(audit trail)* "When the Finanzamt asks, show me how a number was derived —
   including for past years, exactly as they were filed."

The yearly steady-state loop (2026 →): record payments/expenses as they happen all
year → in spring, open Tax Report for last year → review auto-filled numbers +
derivations → export PDF → type into ELSTER. Target: under an hour per year.

## 5. Scope

### Phase 1 — MVP, ship before 2026-07-25 (buffer before the 31st)

**A. Tax profile per property** (one-time setup, new table `property_tax_profiles`):
- purchase_date, purchase_price, building_share_pct (or building value), afa_rate,
  optional afa_note (for pre-Vermio accumulated logic), land registry / unit info
  free-text.
- Computed: yearly AfA + pro-rata first year.

**B. One-off expenses** (new table `expenses`):
- property_id (nullable apartment_id), date, amount, category, vendor/note,
  is_deductible flag, optional `distribute_years` (Erhaltungsaufwand §82b EStDV
  allows spreading large repairs over 2–5 years).
- Categories (= Anlage V groupings): Erhaltungsaufwand, Schuldzinsen,
  Geldbeschaffungskosten, Grundsteuer, Versicherung, Verwaltung, Hausgeld
  (non-umlagefähig part), Fahrtkosten, Sonstige.

**C. Tax-year report** (new endpoint + page "Tax Report"):
- Input: tax year. Output per property (+ grand total):
  - **Income:** sum of `payments.amount` by `payment_date` year (Kaution excluded by
    construction — separate table), grouped rent vs. Umlage when the split is known,
    else total with a "split manually" flag.
  - **Werbungskosten:** AfA (from profile) + expanded recurring `flat_costs`
    (excluding non-deductible types — `Miete`, `Internet`*, `Rundfunk`* configurable)
    + one-off `expenses` for that year (respecting distribute_years).
  - **Result:** Überschuss/Werbungskostenüberschuss per property.
- Every number expandable to its source rows (audit trail = the derivation view).
- **2025 backfill path:** for a year with no payment rows, income lines render as
  **editable manual fields** (pre-filled with contract rent × active months as a
  *suggestion*, clearly marked as estimate). Manual values stored in
  `tax_year_overrides` so re-opening the report shows what was filed.
- **Export:** printable PDF ("Anlage V Ausfüllhilfe 2025 — <property>") + CSV.

**D. Mortgage interest:** MVP = enter the year's interest as a one-off `expenses`
row (category Schuldzinsen) from the bank's Jahreskontoauszug — banks state this
number exactly; no amortization math needed. Rename/deprecate the ambiguous
`Mortgage` flat_cost for tax purposes (excluded from deductible aggregation with a
warning).

### Phase 2 — after the deadline
- Kaltmiete/NK-Vorauszahlung split on contracts → automatic income split.
- Bank CSV import → payments/expenses (also fixes historical gaps).
- Receipt attachments (file per expense row).
- Anlage V PDF laid out to mirror the official form ordering.
- RAG corpus: add Anlage-V / §21 EStG / AfA docs so "Ask Vermio" answers tax
  questions with citations.
- Multi-year comparison + plausibility warnings (expense > 5× last year, missing
  Grundsteuer, etc.).
- **Year lock / filed snapshot:** mark a tax year as "filed" → freeze its report as
  a stored snapshot, so later edits to payments/expenses can't silently change a
  historical filing; show a diff if underlying data has drifted since filing.

### Non-goals (deliberate)
- **No ELSTER submission** (ERiC integration is licensed, heavyweight, and risky to
  ship in days). The module is a *numbers helper*; filing stays in the ELSTER portal.
- No Steuerberater workflows, no Anlage V for Gewerbe/USt cases, no §35a tenant
  statements (that's the Nebenkostenabrechnung module's territory).
- No tax *advice* — the module aggregates; deductibility flags are user-controlled
  defaults with a disclaimer.

## 6. Data model (migrations)

```sql
CREATE TABLE property_tax_profiles (
  id SERIAL PRIMARY KEY,
  property_id INT UNIQUE NOT NULL REFERENCES properties(id),
  purchase_date TEXT,           -- ISO date
  purchase_price NUMERIC,
  building_share_pct NUMERIC,   -- % of price attributable to building
  afa_rate NUMERIC,             -- 2.0 / 2.5 / 3.0, editable
  notes TEXT
);

CREATE TABLE expenses (
  id SERIAL PRIMARY KEY,
  property_id INT NOT NULL REFERENCES properties(id),
  apartment_id INT REFERENCES apartments(id),
  expense_date TEXT NOT NULL,
  amount NUMERIC NOT NULL,      -- EUR, same accounting-currency rule as payments
  category TEXT NOT NULL,
  vendor TEXT, note TEXT,
  deductible INT DEFAULT 1,
  distribute_years INT DEFAULT 1  -- §82b spreading
);

CREATE TABLE tax_year_overrides (      -- manual values for gap years (2025)
  id SERIAL PRIMARY KEY,
  property_id INT NOT NULL REFERENCES properties(id),
  tax_year INT NOT NULL,
  field TEXT NOT NULL,          -- e.g. 'income_total', 'income_umlagen'
  value NUMERIC NOT NULL,
  note TEXT,
  UNIQUE (property_id, tax_year, field)
);
```

`flat_costs` gains nothing; a config map in code decides which `cost_type`s are
deductible by default (Grundsteuer ✓, Hausgeld ✓ with non-umlagefähig caveat,
Verwaltungsbetreuung ✓, Gas/Strom Vorauszahlung ✓ *if* landlord-paid and
re-umlaged, Miete ✗ (that's the landlord's own rent cost type), Mortgage ✗ (see 5D),
Internet/Rundfunk per-property toggle).

## 7. API

```
GET  /api/tax/report?year=2025            → per-property blocks + totals + derivation
GET  /api/tax/profiles                    → list tax profiles
PUT  /api/tax/profiles/{property_id}      → upsert profile
GET/POST/PUT/DELETE /api/tax/expenses     → CRUD, filter by property/year
PUT  /api/tax/overrides/{property_id}/{year}  → set manual fields
GET  /api/tax/report/pdf?year=2025&property_id=…  → Ausfüllhilfe PDF
```

Router `api/routers/tax.py`, mounted with the standard `_auth` dependencies.

## 8. UI (Next.js, new nav group "Taxes")

- **/tax** — year picker (default: last year), property cards with
  income / Werbungskosten / result, expand → derivation table, manual-field editing
  inline for gap years, "Export PDF" per property.
- **/tax/setup** — tax profiles table (one row per property: purchase data → AfA
  preview) + expenses CRUD (year-filtered), reachable via "Setup" tab on /tax.
- Empty states explain the 2025 manual path in one sentence.

## 9. Rollout & timeline (deadline 2026-07-31)

| When | What |
|---|---|
| Day 1–2 | Migrations + `/api/tax/report` (auto parts) + profiles CRUD |
| Day 3 | Expenses CRUD + overrides + AfA math + tests (pure functions, same style as `test_detect_overdue`) |
| Day 4 | /tax page + setup page |
| Day 5 | PDF export, polish, deploy |
| Rest of month | **User enters 2025 data** (profiles, interest, one-offs, manual income), files via ELSTER |

Risk buffer: if PDF slips, CSV + screen numbers are sufficient to file.

## 10. Decisions (resolved 2026-07-19)

1. **2025 income source:** contract-based estimates, corrected manually against bank
   statements in editable fields. Bank-CSV import deferred to Phase 2. ✅
2. **AfA:** purchase data available for all properties → full AfA setup in MVP.
   (If any property was inherited/gifted, AfA continues from the predecessor —
   flag those during setup.) ✅
3. **Filing mode:** self-filed via ELSTER portal → deadline **2026-07-31** stands,
   MVP timeline as in §9. ✅

## 11. Remaining open questions (non-blocking, resolve during build)

1. **Hausgeld:** enter the umlagefähig/non-umlagefähig split from the
   WEG-Abrechnung (accurate) or deduct full Hausgeld (simpler, slightly wrong)?
2. Were any of the 8 properties **self-occupied or vacant** parts of 2025?
   (Affects deductibility share per property.)

---
*Disclaimer baked into the UI: aggregation aid, not tax advice (keine Steuerberatung).*
