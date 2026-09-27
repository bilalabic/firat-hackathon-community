# Stack Research

Research date: 2026-09-27. Sources are official documentation unless noted. "Pass 1" was the initial finding and "Pass 2" was the challenge.

## 1. Local developer machine (verified)

| Item | Found | Consequence |
|---|---|---|
| OS | Windows 11 Pro 26200 | Windows-native by default |
| Node.js / pnpm / npm | v24.21.0 / 12.4.2 / 11.19.0 | Frontend tooling is ready |
| Python (Windows) | Was missing → **CPython 3.12.14 managed by uv** (installed 2026-09-28, `uv python install 3.12`; no global Python, Store alias untouched) | Backend can run natively |
| uv (Windows) | Was missing → **uv 0.12.16** via `winget install astral-sh.uv --scope user` (2026-09-28) | — |
| Python / uv (WSL Ubuntu-24.04) | 3.12.3 / uv 0.12.15 | Possible fallback, but CLAUDE.md prefers Windows-native |
| Docker | 29.7.2 | Supabase local stack is possible |
| Ollama | Was missing → **0.34.2** via `winget install Ollama.Ollama` (2026-09-28); listens on 127.0.0.1:11434; CUDA detected, 6.8 GiB available | No models pulled yet |
| Supabase CLI | Not installed | Use the `supabase` npm package as a devDependency (no global install) |
| GPU | RTX 5070 Laptop, 8151 MiB, driver 616.92 | Supported by Ollama (compute capability 12.0 is listed; driver ≥ 550 is required) |
| RAM | 31 GB (WSL sees 15 GB) | Enough for partial CPU offload of models around 9B |

## 2. Next.js (public web + admin)

- Current: **Next.js 16.3** (2026-08-03); docs version 16.3.6. Turbopack is the default bundler since 16.0.
- Caching: **Cache Components** (`cacheComponents: true`) with `'use cache'`, `cacheLife`, `cacheTag`. The previous model is still documented separately.
- On-demand revalidation from outside the app: in a Route Handler, `revalidateTag(tag, { expire: 0 })` expires immediately. `updateTag` works only in Server Actions. The single-argument `revalidateTag(tag)` form is deprecated.
- `next/og` `ImageResponse` (Satori + Resvg) converts JSX to PNG. It supports flexbox only (no grid) and has a 500 KB bundle limit. Only `ttf`, `otf` and `woff` fonts work (no `woff2`). It works in Route Handlers and in `opengraph-image.tsx`.

Pass 2: Cache Components changes the mental model (a Suspense boundary is needed around runtime data). The public site is mostly static lists, which fits well. Risk: code copied from older tutorials will use the previous caching model. Mitigation: follow the 16.x docs and note it in `PUBLIC_WEB.md`.

## 3. shadcn/ui

- `dashboard-01` block exists: `npx shadcn add dashboard-01`. It contains `AppSidebar` (inset), `SiteHeader`, `SectionCards`, `ChartAreaInteractive`, and `DataTable` (fed from `data.json`).
- Init for Next.js: `pnpm dlx shadcn@latest init -t next`. It supports `--monorepo`.
- Pass 2: the `--monorepo` template creates a shared `packages/ui`. We **do not** use it in V1. There are only two apps, and shadcn copies components into each app anyway. A shared UI package adds build wiring with no V1 benefit. Revisit this if duplicated components drift.

## 4. Supabase

Verified facts:

1. **API keys.** Use the new `sb_publishable_…` and `sb_secret_…` keys. Legacy `anon` and `service_role` keys "keep working until the end of 2026", so a V1 built on legacy keys would break within about 3 months. Secret keys bypass RLS and return 401 when the User-Agent looks like a browser.
2. **Default grants are changing.** New tables in `public` historically got automatic grants to `anon` and `authenticated`. Supabase is moving the default to revoke these grants. The docs recommend exposing a **dedicated API schema** (e.g. `api`) and keeping internal tables in unexposed schemas.
3. **RLS** must be enabled on every table in an exposed schema. Views bypass RLS unless they are created with `security_invoker = true`.
4. **Connections from a long-running backend:** a direct connection (port 5432) is IPv6-only without the IPv4 add-on. The **session-mode pooler** (port 5432 on the pooler host) supports IPv4 on all plans and supports prepared statements. Transaction mode (6543) does not support prepared statements.
5. **Free plan pausing:** a free project inactive for 7 days is paused. Any API request resets the timer. Paid projects are never paused. Sources: [Supabase docs, Project Pausing](https://supabase.com/docs/guides/platform/free-project-pausing); pricing page. A secondary source says that projects paused for a long time are eventually deleted. This is not verified in official docs yet.

Pass 2 challenges:
- *"Is Supabase needed at all? Could the admin push static JSON to the repo like today?"* That would keep a git-as-database model: no private data, no forms, no publication history. Public forms need a private write-only store. **Supabase stays.**
- *"Neon or plain Postgres instead?"* Supabase adds the Data API with RLS, which lets the public site read and write without running our own server. It also has a local Docker stack (`supabase start`) and SQL migrations. Neon would require building an API layer on Vercel. **Supabase stays.**
- *Pause risk* is real for a low-traffic community site. Mitigations: daily keep-alive request (GitHub Actions cron), or Pro plan. **Requires owner decision** (see DECISIONS D-03).

## 5. Python backend

- FastAPI + Pydantic v2 + `pydantic-settings`.
- DB driver: **psycopg 3** with a connection pool. Plain SQL in repository modules.
- Migrations: **Supabase CLI SQL migrations only** (`supabase/migrations/*.sql`). We do not use Alembic, because two migration systems for one database is a known failure mode.
- Quality: `ruff` (lint + format), `mypy` (with the pydantic plugin), `pytest`.
- Pass 2: *"Why not SQLAlchemy ORM?"* The schema is owned by SQL migrations, RLS and functions live in SQL, and the team is small. An ORM would duplicate the schema definition. Plain SQL with Pydantic models is enough. Revisit if the query count grows past about 50.

## 6. Why two runtimes (Python + TypeScript)

Pass 1: Next.js admin → FastAPI → Postgres.

Pass 2 (challenge): an all-TypeScript admin (Next.js Server Actions writing to Postgres) would remove one runtime for V1.

Resolution: V1.2+ needs Python-first libraries (trafilatura, RapidFuzz, Playwright for Python, Pydantic-schema structured outputs with Ollama). The existing automation is already Python. If V1 writes from TypeScript, business rules (state transitions, dedup, publication hashing) would later exist in two languages.
**Decision: FastAPI is the only writer of canonical data. The admin Next.js app is a UI with no database credentials.** The public web never writes canonical tables; it only calls two narrow insert functions.

## 7. Frameworks explicitly rejected for V1

| Candidate | Reason |
|---|---|
| LangChain / LangGraph / CrewAI / AutoGen | The pipeline is a fixed sequence (fetch → extract → validate → dedup → review). Plain functions are clearer and testable. |
| LiteLLM | Adds a large dependency for routing we can do in about 100 lines. Also, PyPI versions 1.82.7/1.82.8 were compromised on 2026-03-24 (supply-chain attack; [LiteLLM security update](https://docs.litellm.ai/blog/security-update-march-2026)). This is a reminder to keep the dependency surface small. |
| Crawl4AI | Browser-first (Playwright under the hood) and includes "undetected" browsing modes we do not want. It adds nothing over httpx + trafilatura, with Playwright as a fallback. See CRAWLING_RESEARCH. |
| Redis, queues, vector DB, GraphQL, microservices | No V1 requirement. |
