# Vermio — Frontend

Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui + Recharts UI for
the Vermio property-management system. It talks to the FastAPI backend over REST
with a JWT Bearer token.

For the full project (Docker setup, backend, database, scripts), see the
[root README](../README.md).

## Develop

```bash
npm install --legacy-peer-deps
npm run dev          # http://localhost:3000
```

Point the app at the API by setting it in `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

`NEXT_PUBLIC_API_URL` is read at **build time**, so the Docker image bakes it in
via the `NEXT_PUBLIC_API_URL` build arg (see `docker-compose.yml`).

## Build

```bash
npm run build        # production build
npm run start        # serve the production build
```

## Layout

```
app/
  (app)/             # authenticated pages (dashboard, contracts, nebenkostenabrechnung, …)
  login/             # login page
lib/                 # api client (axios + auth interceptor), types, helpers
components/           # shared UI (shadcn/ui wrappers, page chrome)
```

Auth: the JWT is stored in `localStorage` under `token`; `lib/api.ts` attaches it
to every request and redirects to `/login` on a 401.
