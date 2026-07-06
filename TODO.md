# TODO — Improvements & Findings

System review of the FastAPI + Next.js + PostgreSQL stack. Items are grouped by
severity. Checkboxes track progress.

---

## 🔴 Security (fix before any non-localhost deployment)

- [x] **Authenticate the signature endpoints.**
  `GET/POST /api/signature` and `GET /api/signature-pad` were registered directly
  on `app`, bypassing `require_auth`.
  - Done: `_check_signature_access()` validates a token from the `Authorization`
    header or a `?token=` query param (needed because `<img>`/`<iframe>` can't set
    a header). Open when `APP_PASSWORD_HASH` is unset (no regression). The pad
    injects the caller's token into its POST; the Settings page passes the token
    to both the `<img>` and the pad `<iframe>`.

- [x] **Set real secrets in production.**
  `JWT_SECRET` defaults to the hardcoded string `change-this-in-production-32chars`
  in `docker-compose.yml`; with it unset, tokens can be forged. `APP_PASSWORD_HASH`
  empty = fully open access.
  - Done: `auth.verify_startup_config()` runs in the FastAPI lifespan. With
    `APP_ENV=production` it refuses to start when `JWT_SECRET` is unset/placeholder
    or `APP_PASSWORD_HASH` is empty; in dev it only logs a warning. `APP_ENV` is
    documented in `.env.example`.

---

## 🟠 Performance

- [ ] **Collapse `payment-reminders` into a single query.**
  `api/routers/reports.py` → `detect_overdue(months_back=12)` runs ~12 payment
  queries per active contract, then the endpoint adds one more `meta` query per
  overdue contract for the property name (N+1 ×2). On Neon (~30–50 ms/query) this
  is the slowest endpoint. Replace with one JOIN + grouped subquery.

---

## 🟡 Minor / UX

- [x] **Refresh the contract detail view after Kaution/terminate mutations.**
  `frontend/app/(app)/contracts/page.tsx` — terminate/reopen/mark-returned/
  clear-return and edit-save now update `selectedContract` from the mutation
  response (each endpoint returns the fresh contract), so the open detail card
  is no longer stale.

- [x] **Remove the explicit `DELETE FROM payments` in `delete_contract`.**
  `api/routers/contracts.py` — removed; `ON DELETE CASCADE` handles it (verified
  the live FK is CASCADE).

- [x] **Clean up stale create-next-app docs.**
  `frontend/AGENTS.md` claimed "this is NOT the Next.js you know" and pointed at a
  non-existent `node_modules/next/dist/docs/` path; the project runs standard
  Next 14. Replaced with accurate project guidance; `frontend/CLAUDE.md` imports
  it via `@AGENTS.md`. `frontend/README.md` boilerplate also replaced.

---

## ✅ Verified solid (no action needed)

- No SQL injection: f-strings only interpolate static WHERE fragments; all user
  values are parameterized. `_adapt` `%`→`%%` escaping is correct and raw cursor
  queries correctly bypass it.
- Decimal→float JSON serialization handled (balance-sheet `_f()`, explicit
  `float()` in kaution-overview / payments).
- PDF endpoints read file bytes correctly; billing-profile loader handles both
  both the legacy and current billing-profile schemas.
- TanStack Query v5 usage correct (no `onSuccess` on `useQuery`).
- FK constraints correct (RESTRICT on contracts→tenants/apartments, CASCADE on
  child rows); contract delete is safe.
- Cross-platform Docker networking via `setup.sh` joining `landlord-pg` to the
  compose network.

---

## Future / nice-to-have

- [ ] Email sending for Mahnung (SMTP config exists in Settings but the send flow
      isn't wired into the Next.js UI — only "log reminder" is).
- [ ] Edit Payment in Rent Tracking (currently add/delete only).
- [x] Tests: pure calculation logic now covered — `backend/tests/` has a pytest
      suite for `logic.py` (Nebenkosten proration), `currencies.py`, `db._adapt`
      (SQL translation), and the auth startup guard. Run with `make test` or
      `cd backend && pytest`. Still todo: integration tests for the DB-backed
      routers (`detect_overdue`, `tenant_ledger`, balance-sheet snapshot).
