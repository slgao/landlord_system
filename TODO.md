# TODO — Improvements & Findings

System review of the FastAPI + Next.js + PostgreSQL stack. Items are grouped by
severity. Checkboxes track progress.

---

## 🔴 Security (fix before any non-localhost deployment)

- [ ] **Authenticate the signature endpoints.**
  `GET/POST /api/signature` and `GET /api/signature-pad` are registered directly
  on `app` in `api/main.py`, bypassing the `require_auth` dependency that guards
  every `/api/*` router. An unauthenticated caller can overwrite the landlord's
  signature PNG (`POST`) or read it.
  - Trade-off: the Settings page loads the signature through an `<iframe>`/`<img>`
    that cannot send a `Bearer` header. It currently passes `?token=` in the query
    string, which the endpoint ignores.
  - Fix: validate a query-param token on these routes (or move to a short-lived
    signed URL) and update `frontend/app/(app)/settings/page.tsx` accordingly.

- [ ] **Set real secrets in production.**
  `JWT_SECRET` defaults to the hardcoded string `change-this-in-production-32chars`
  in `docker-compose.yml`; with it unset, tokens can be forged. `APP_PASSWORD_HASH`
  empty = fully open access.
  - Document required prod env vars and fail fast (refuse to start) when
    `JWT_SECRET`/`APP_PASSWORD_HASH` are unset outside local dev.

---

## 🟠 Performance

- [ ] **Collapse `payment-reminders` into a single query.**
  `api/routers/reports.py` → `detect_overdue(months_back=12)` runs ~12 payment
  queries per active contract, then the endpoint adds one more `meta` query per
  overdue contract for the property name (N+1 ×2). On Neon (~30–50 ms/query) this
  is the slowest endpoint. Replace with one JOIN + grouped subquery.

---

## 🟡 Minor / UX

- [ ] **Refresh the contract detail view after Kaution/terminate mutations.**
  In `frontend/app/(app)/contracts/page.tsx`, `selectedContract` is a snapshot
  taken at `openDetail`. After "Mark Returned" / terminate / reopen, the list
  refetches but the open detail card shows stale `kaution_returned_date` until
  reopened. Re-derive `selectedContract` from the live query data.

- [ ] **Remove the explicit `DELETE FROM payments` in `delete_contract`.**
  `api/routers/contracts.py` — redundant because the FK is `ON DELETE CASCADE`.
  Harmless, but misleading. Low priority.

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
- [ ] Tests: no automated test suite yet for the API routers or calculation logic.
