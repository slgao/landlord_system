# Frontend agent notes

This is a **standard Next.js 14 (App Router)** app — TypeScript, Tailwind CSS,
shadcn/ui, Recharts, TanStack Query v5. Nothing exotic; your normal Next 14
knowledge applies. See [README.md](./README.md) for dev/build commands.

## Things that bite

- **`NEXT_PUBLIC_API_URL` is inlined at build time.** The production Docker image
  has no source volume, so frontend changes require a rebuild to take effect:
  `docker-compose build frontend && docker-compose up -d frontend`.
- **API access:** use the axios client in `lib/api.ts` (it attaches the JWT and
  redirects to `/login` on 401). PDF endpoints are hit with raw `fetch` because
  the response is a binary blob — surface errors and check `res.ok` explicitly.
- **Auth:** the JWT lives in `localStorage` under `token`. Pages under
  `app/(app)/` are the authenticated area.
- **Types** live in `lib/types.ts`; keep them in sync with the FastAPI schemas.

## Before you call it done

- Run `npx tsc --noEmit` (the project must typecheck).
- If you changed anything served in the browser, rebuild the frontend image —
  a passing typecheck does not mean the running container is updated.
