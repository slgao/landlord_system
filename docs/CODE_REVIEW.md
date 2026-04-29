# Codebase Review & Improvement Suggestions

A prioritized walkthrough of the landlord management system, focused on what would matter to take it from "personal tool" to "product I'd put in front of paying customers."

---

## 1. Critical issues (data integrity & correctness)

### 1a. Money as `float` is dangerous
`db._normalize` converts every `Decimal` to `float` so legacy SQLite-era code keeps working (`db.py:42-49`). For an accounting app this is the wrong tradeoff — `0.1 + 0.2 != 0.3`, and you'll get cents-off mismatches in balance sheets, Kaution balances, and Nachzahlung totals once volumes grow. Switch to `decimal.Decimal` end-to-end (Postgres `NUMERIC` already supports it; Pydantic v2 has `Decimal` field type; ReportLab handles it via `str()`).

### 1b. Dates as `TEXT` columns
Every date is stored as `YYYY-MM-DD` text (`start_date`, `end_date`, `payment_date`, `valid_from/to`, `reading_date`, `kaution_paid_date`). Symptoms throughout the codebase:
- `WHERE end_date IS NULL OR end_date = 'None'` — the literal string `"None"` from a buggy `str(None)` write persists in the data and now haunts every query (e.g. `contracts.py:18`, `rent_tracking.py:67`, `flat_costs.py:22`).
- Comparisons rely on lexicographic ordering of ISO strings (works, but only by accident).
- No DB-level validation, you can't index efficiently for date ranges, and you can't use Postgres date functions cleanly.

Migrate to `DATE` / `TIMESTAMPTZ` columns. One Alembic migration + a backfill (`UPDATE … SET end_date = NULLIF(end_date, 'None')::DATE`).

### 1c. Schema defined in two places (db.py **and** Alembic)
`db.init_db()` creates tables and runs ALTER TABLE migrations imperatively (`db.py:52-252`). Alembic also has 4 migrations under `alembic/versions/`. They will drift — and on a fresh install, `init_db()` runs first and Alembic sees the tables already exist. Pick one source of truth: I'd kill `init_db()`, generate an Alembic baseline that captures current schema exactly, and rely on `alembic upgrade head` in `setup.sh` and FastAPI startup. (You already have alembic — just commit to it.)

### 1d. SQL injection vector via f-string interpolation
`page_modules/meter_readings.py:43-46` builds SQL like:
```python
f"WHERE ((COALESCE(scope,'room') = 'room' AND apartment_id = {apartment_id}) ...)"
```
`apartment_id` comes from a Streamlit selectbox so today it's safe, but it's a foot-gun pattern that will bite when copy-pasted. Use parameterized queries everywhere; never f-string user-derived values into SQL — even integers.

### 1e. No FK constraints
None of your tables declare foreign keys. Delete a property and apartments/contracts orphan; delete a contract and its payments+kaution_deductions+co_tenants+reminders orphan. Add `REFERENCES … ON DELETE CASCADE` (or `RESTRICT` and handle in app), and check existing data for orphans first.

### 1f. Polymorphic association without integrity
`meter_readings(meter_type TEXT, meter_id INTEGER)` points to one of 4 tables based on `meter_type` (`db.py:199-211`). No FK can enforce this. Either (a) one row per meter type (4 nullable FKs + CHECK constraint) or (b) one shared `meters` table with a `kind` discriminator. Option (b) cleans up `_fetch_meters_for_apartment` significantly.

---

## 2. Architecture

### 2a. The FastAPI layer is a stub the UI doesn't use
`api/` exposes basic CRUD for properties/apartments/tenants/contracts/payments, but every Streamlit page calls `db.fetch/execute` directly. The actual high-value logic (Nebenkostenabrechnung, Mahnung, balance sheet, overdue detection) doesn't have an API at all. Result: the API is dead weight that drifts from reality, and you'll be in trouble when the planned Next.js frontend (mentioned in `api/main.py:18`) needs the real features.

Pick a direction:
- **If the API is the future**: move all DB queries + business logic into a `services/` package, have both Streamlit and FastAPI call those services. Then `api/routers/contracts.py` and `page_modules/contracts.py` share `services.contracts.list_active(…)`.
- **If Streamlit is forever**: delete `api/` until you actually need it. Less code, less drift.

### 2b. No service / repository layer — JOINs duplicated everywhere
The `contracts ⋈ tenants ⋈ apartments ⋈ properties` join appears verbatim in `contracts.py`, `rent_tracking.py`, `balance_sheet.py`, `payment_reminders.py`, `tenants.py`, `mahnung.py`, and four routers. When you add a column or change cardinality, you'll edit 8 places. Extract:

```python
# services/contracts.py
def list_with_relations(active_only=False) -> list[Contract]: ...
def get_status(contract: Contract, today: date) -> ContractStatus: ...
```

`_contract_status` exists in 4 versions (rent_tracking, contracts, tenants, dashboard) with subtle differences in how `terminated`, `'None'`, and missing dates are handled — these inconsistencies are bugs waiting to happen. One source of truth.

### 2c. Page modules are 200–1400 lines mixing UI + SQL + logic
`nebenkostenabrechnung.py` (1370 lines!) holds session-state plumbing, persistence, and rendering all together. `contracts.py` (496) does Kaution accounting, contract lifecycle, co-tenants, deletion. Split each page into:
- `page_modules/<name>.py` — `show()` + Streamlit widgets only
- `services/<domain>.py` — DB access + computations
- `domain/<name>.py` — pure dataclasses / pydantic models

This makes everything testable (the current code is essentially untestable because it depends on `st.session_state` and `db.fetch`).

### 2d. Connection-per-query
`db.get_conn()` opens a new psycopg2 connection on every `fetch`/`execute` (`db.py:23-24`, called ~1300 times across the codebase). Streamlit page renders fire dozens of queries — each is a TCP round-trip + auth handshake. Move to a connection pool (`psycopg2.pool.SimpleConnectionPool` or switch to SQLAlchemy + its pooling). On the same machine the latency is small, but on a remote DB this matters a lot.

### 2e. No transactions across operations
Every `execute()` auto-commits and closes. Anything that should be atomic isn't:
- Recording a Kaution deduction + updating the open balance metric
- Move-out (set `terminated=1`, set `end_date`, archive payments)
- Importing meter readings in bulk

A `with db.transaction(): …` context manager is the minimal step.

---

## 3. Security (matters most when you go beyond localhost)

### 3a. No authentication anywhere
Streamlit and FastAPI are both wide open. Today that's fine because we just bound them to localhost — but the moment you put this on a VPS for a customer, anyone who knows the URL is in. Recommendation:
- For Streamlit: use `streamlit-authenticator` for a quick single-user gate, or front it with an OAuth proxy (Authelia / oauth2-proxy / Cloudflare Access).
- For FastAPI: actual JWT or session auth (`fastapi-users` is the path of least resistance). You already include `python-jose` and `passlib[bcrypt]` in requirements but never use them.

### 3b. SMTP credentials stored plaintext in `config` table
`payment_reminders.py:60-67` writes the SMTP password into the `config` table as TEXT. If the DB ever leaks (backup, accidental dump in a screenshot), all SMTP creds are exposed. At minimum, encrypt them with a key from `.env` (`cryptography.fernet`), or stop persisting and require them in `.env`.

### 3c. Signature upload has no validation
`nebenkostenabrechnung.py:166-172` writes any uploaded file with `.png/.jpg/.jpeg` extension to `pdf/signature.png` without checking magic bytes, size, or dimensions. Mostly harmless on a single-user app, but worth tightening if multi-tenant.

### 3d. CORS allows credentials from `localhost:3000` even though there's no Next.js client yet
Harmless until something exists at that origin. Fine to leave; just be aware.

---

## 4. Code quality

### 4a. Pin your dependencies
`requirements.txt` has 10 unpinned packages. Streamlit had a major UX overhaul in 1.30+; psycopg2 has a 3.x rewrite. A blind `pip install -r requirements.txt` six months from now may install incompatible versions. Generate a `requirements.lock` (or move to `uv` / `poetry` / `pip-tools`).

### 4b. Boolean as INTEGER
`contracts.terminated INTEGER DEFAULT 0`, `co_tenants.in_contract INTEGER DEFAULT 0` — Postgres has `BOOLEAN`. The current code does `COALESCE(terminated, 0) = 0` everywhere, which would simplify to `NOT terminated`.

### 4c. No tests, no CI, no linter
No `tests/`, no `pytest`, no GitHub Actions, no `ruff`/`black`/`mypy`. The `logic.py` calculation functions (`strom_calc_detail`, `gas_calc_detail`, `betriebskosten_calc`) are pure and would be trivial to unit-test — and *should* be, because incorrect Nebenkostenabrechnung is a legal liability in Germany.

Minimum starter:
- `pytest` + a `tests/test_logic.py` covering calc functions with realistic edge cases (mid-period move-in, leap year, zero consumption, vacant flat).
- `ruff check` in pre-commit and CI.
- `mypy --strict` on `services/` and `logic.py` once those exist.

### 4d. Dead code & repo hygiene
- `logic.dashboard_stats()` (`logic.py:251-268`) is unused — `dashboard.py` calls `fetch` directly.
- `.env_bak`, `.app.py.~undo-tree~` and other `.~undo-tree~` files in repo (Emacs leftovers). Add `*.~undo-tree~` to `.gitignore` and delete the existing ones.
- `__pycache__/` checked in inside `alembic/versions/`.
- The `Copyright (C) 2026 * Ltd. All rights reserved.` header at the top of every file conflicts with the OSS license. Either remove the headers or pick a license stance.

### 4e. The `_adapt` SQL translator is a footgun
`db._adapt` does `% → %%` and `? → %s` (`db.py:27-39`). It works, but it's bespoke. Any future contributor will trip on the `%%` escape and the `'None'` string. SQLAlchemy Core (or full ORM) eliminates this entire layer for free, gives you a connection pool, and sets you up for the schema unification in 1c.

---

## 5. UX & product polish

### 5a. State leaks across reruns
Streamlit reruns the entire script on every interaction. Many pages mutate session state directly (`nebenkostenabrechnung.py:14-138` is 100+ session keys). Wrap save-and-submit operations in `st.form` so the form fields don't trigger reruns mid-edit.

### 5b. Date inputs default to "today" everywhere
`Edit Contract` calls `date.fromisoformat(c_start)` for the start date — good — but for `End date` defaults to `date.today()` if missing. Subtle UX trap: a user opening the edit dialog on a contract without an end date and ticking "Fixed Term" suddenly sees today's date as if it were saved. Better: open with a sentinel and require the user to pick.

### 5c. Selecting a contract by `format_func` returning a multi-field tuple
Many selectboxes do `st.selectbox(..., contract_data, format_func=lambda x: f"#{x[0]} — {x[1]} / {x[2]}")` then index `[0], [3], [5], [8]` from the row. If the SELECT order changes upstream, all selectors silently break. Use namedtuples or `@dataclass` for query rows — adds compile-time-ish safety.

### 5d. Accessibility & i18n inconsistency
Mix of English UI (`Tenants`, `Apartments`, `Balance Sheet`) and German domain terms (`Kaution`, `Mahnung`, `Nebenkostenabrechnung`). Consistent for German landlords, but if you sell outside DE you'll need a real i18n layer. `streamlit-i18n` exists; or just centralize all labels in a `strings.py` module now.

---

## 6. The Streamlit ceiling

Streamlit is great for internal tools but has known limits for SaaS:
- Single-user mental model (multi-user works, but state collisions are easy).
- No row-level URL state — can't deep-link to a contract page.
- Render-everything-on-rerun makes complex flows feel sluggish.
- Limited control over auth, layout, mobile.

If "professional" means selling to multiple landlords, the trajectory is probably:
1. Now: harden the FastAPI layer to cover *all* domain operations, not just CRUD on 5 tables.
2. Build a Next.js (or SvelteKit) admin app on top of that API.
3. Keep Streamlit around for one-off ops dashboards.

But if "professional" means polish for personal use + screenshots, Streamlit is fine — focus on items 1, 2b, 2c, 4a, 4c.

---

## Suggested order of attack

If I were going to spend a week on this, I'd do:

| Day | Task | Why |
|-----|------|-----|
| 1 | Add pytest + tests for `logic.py` calculations | Locks correctness before refactoring |
| 1 | Pin `requirements.txt`, add `ruff` + pre-commit | Foundation for everything else |
| 2 | Migrate to `DATE`/`BOOLEAN` columns + Alembic baseline; remove `init_db()` | Eliminates the `'None'` string class of bugs |
| 3 | Add FK constraints with cascading; fix orphan handling | Data integrity |
| 3 | Switch `Decimal` end-to-end | Accounting correctness |
| 4 | Extract `services/` layer; collapse the 4 versions of `_contract_status` | Maintainability |
| 5 | Add basic auth (Streamlit + FastAPI) | Required before any deployment |
| 5 | Add SQLAlchemy + connection pool, drop `_adapt` | Cleans up the SQL layer for everything that follows |
