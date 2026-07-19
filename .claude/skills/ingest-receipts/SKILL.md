---
name: ingest-receipts
description: Read scanned bills/receipts (PDFs) under documents/ and create tax-module expense rows from them, with source_file back-references. Args - a folder like documents/2025 or a single PDF path.
---

# Ingest scanned receipts into the tax module

Turn scanned bills under `documents/<year>/<property>/` into `expenses` rows
via the tax API, so the Anlage-V report aggregates them with a per-receipt
audit trail.

## Steps

1. **Resolve scope.** The argument is a folder (default: `documents/<last year>`)
   or a single PDF. Find PDFs with `find <scope> -iname '*.pdf'`.
2. **Load property list** from `GET /api/tax/profiles` (dev API on
   `localhost:8000`; obtain a token via `POST /api/auth/token` — any
   credentials work in open mode). Match each PDF's `<property>` folder name
   against property names (fuzzy: prefix/substring match is fine, ask the user
   only when genuinely ambiguous).
3. **Read each PDF** with the Read tool. Extract:
   - `expense_date` — the PAYMENT date if visible, else invoice date (ISO).
   - `amount` — gross EUR total (Brutto).
   - `vendor` — company name.
   - `category` — one of `GET /api/tax/expense-categories`. Guidance:
     roof/plumbing/heating repairs → Erhaltungsaufwand; painting/renovation →
     Renovierung; maintenance contracts (Wartung) → Instandhaltung; insurance →
     Versicherung; property tax bill → Grundsteuer; WEG-Abrechnung → Hausgeld;
     loan interest statement (Jahreskontoauszug) → Schuldzinsen; else Sonstige.
   - `note` — one line: what the bill is for (German OK).
4. **Duplicate check.** `GET /api/tax/expenses?property_id=<id>` — skip files
   whose `source_file` already exists in a row (re-runs must be idempotent);
   also flag same-date+same-amount rows as likely duplicates and ask.
5. **Create rows** with `POST /api/tax/expenses`, always setting
   `source_file` to the repo-relative PDF path. Use `distribute_years > 1`
   only if the user asked to spread a large repair (§82b), never by default.
6. **Warn, don't decide,** when: a single repair bill exceeds ~15% of a
   property's building purchase price within 3 years of purchase
   (anschaffungsnaher Aufwand risk — needs the user's judgment), the PDF is
   unreadable/scanned upside down, or the amount/date is ambiguous.
7. **Report** a table: file → property, date, amount, category, created/skipped,
   plus the per-property totals now visible in `GET /api/tax/report?year=<year>`.
8. **Generate the Belegliste PDF.** After all files are processed, download
   the billing inventory — every bill of the year listed per property
   (date, category, vendor, flat, Beleg file, amount) with per-property
   subtotals and a grand total across all flats — and save it next to the
   receipts:

       curl -H "Authorization: Bearer $TOKEN" \
         "localhost:8000/api/tax/expenses/inventory/pdf?year=<year>" \
         -o "documents/<year>/Belegliste_<year>_$(date +%F).pdf"

   Tell the user the path. The date suffix keeps earlier runs as history.

Never modify or move the PDFs. Never push `documents/` (gitignored).
