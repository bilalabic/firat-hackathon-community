# System Architecture

Status: **Final proposal for V1. Awaiting owner approval** (see `docs/planning/DECISIONS.md`).

## 1. First proposal (Stage C)

```text
Laptop:  Admin Next.js ──► FastAPI ──► Supabase Postgres ◄── Public Next.js (Vercel)
                            │  └─► Ollama
                            ├─► Telegram Bot API
                            └─► local SQLite (crawler cache)
Public forms → Supabase (anonymous insert)
Event cards → Playwright screenshots in FastAPI
```

## 2. Second review (Stage D): challenges and results

| # | Challenge | Finding | Change |
|---|---|---|---|
| R1 | Overengineering: two runtimes on the laptop | Justified by Python-only needs from V1.2 onward. The risk is logic duplication, not runtime count | Admin Next.js gets **no DB credentials**. FastAPI is the single writer |
| R2 | Supabase mistake: anonymous insert into `public` tables | `public` exposure and default grants are being tightened by Supabase. Direct table inserts expose table shape and allow bypassing validation | Tables live in unexposed schema `app`. Only schema `api` is exposed, with **one read view + two insert functions** |
| R3 | Supabase mistake: legacy `anon`/`service_role` keys | They stop working after **end of 2026** | Use `sb_publishable_…` (Vercel) and a direct Postgres connection string (FastAPI). No secret API key is needed anywhere in V1 |
| R4 | Vercel holding a service-role or secret key | A leak would give full DB access from an internet-facing app | Vercel gets only the publishable key, used server-side only |
| R5 | Local/cloud coupling: public site depends on laptop | Must not. Web reads Supabase directly; the laptop only pushes cache invalidations | Revalidation is best-effort; `cacheLife` time expiry is the fallback |
| R6 | Unnecessary service: local SQLite | V1 has no crawler. In V1.2, a filesystem cache (`.cache/fetch/<sha256>.html`) is enough | **SQLite removed** |
| R7 | Image pipeline: Playwright screenshots in FastAPI | Heavy (Chromium) for a single template. The public site needs OpenGraph images anyway | Card = public site's `opengraph-image` route (Satori). Telegram sends it by URL. One template, two uses |
| R8 | R7 creates an ordering constraint: the OG route only renders public events | Acceptable, because the website is the canonical publication and Telegram links to it | Flow: approve → publish on web → Telegram preview → post. Revisit if a Telegram-only event is ever needed |
| R9 | Security: localhost API reachable by any website in the browser (CSRF / DNS rebinding) | Real risk for `localhost:8000` | FastAPI binds `127.0.0.1`, uses `TrustedHostMiddleware` (`localhost`, `127.0.0.1`), requires a bearer token, and CORS is closed (browser never calls it directly) |
| R10 | AI misuse: LLM deciding duplicates or dates | Deterministic checks first; the LLM only proposes, with evidence snippets | See AI_ARCHITECTURE |
| R11 | Migration problem: two migration tools | Only Supabase CLI SQL migrations; no Alembic | — |
| R12 | Future migration: GitHub Pages URL already shared | Pages cannot redirect server-side | Keep a meta-refresh + link page at the old URL after cutover |
| R13 | Free-tier pause (7 days inactivity) | Could take the public site's data offline | Owner decision: keep-alive cron vs Pro (D-03) |
| R14 | Vercel Hobby = non-commercial only | A donation/"Support" page may be judged commercial | Owner decision (OPEN_QUESTIONS Q3) |
| R15 | Shared `packages/` for types/UI | No V1 need; adds build wiring | No shared packages. Web types come from `supabase gen types`; admin types from FastAPI OpenAPI |

## 3. Final architecture (Stage E)

```text
┌──────────────────────── Developer laptop (never exposed) ────────────────────────┐
│                                                                                  │
│  Admin UI  (Next.js 16, :3001)  ──server-side fetch + bearer──►  API (FastAPI,   │
│   shadcn dashboard-01                                             127.0.0.1:8000)│
│   no DB credentials                                               │  │  │        │
│                                                                   │  │  └─► Ollama (:11434)
│                                                                   │  └────► Telegram Bot API (HTTPS, outbound)
│                                                                   └──psycopg (session pooler, TLS)──┐
└──────────────────────────────────────────────────────────────────────────────────┼┘
                                                                                   ▼
                                         ┌──────────── Supabase (cloud) ────────────┐
                                         │ Postgres                                  │
                                         │  schema app  (tables, RLS on, not exposed)│
                                         │  schema api  (exposed via Data API):      │
                                         │    view  api.events_public                │
                                         │    fn    api.submit_community_application │
                                         │    fn    api.submit_team_application      │
                                         └───────────────▲───────────────────────────┘
                                                         │ publishable key (server-side only)
┌──────────────────────── Vercel ────────────────────────┴─────────┐
│ Public web (Next.js 16, Cache Components)                         │
│  pages: hackathons, event detail, community, contribute, about    │
│  /events/[slug]/opengraph-image  → PNG card (also used by Telegram)
│  POST /api/revalidate  (shared secret) ◄── called by FastAPI       │
└───────────────────────────────────────────────────────────────────┘
```

### Responsibilities

| Component | Owns | Never does |
|---|---|---|
| FastAPI (`services/api`) | All canonical writes, state transitions, validation, normalization, publication records, Telegram calls, LLM calls | Serve the public; accept requests from non-localhost hosts |
| Admin (`apps/admin`) | Operator UI, previews | Hold DB, Telegram or LLM credentials |
| Public web (`apps/web`) | Read published events, render cards/SEO, forward form submissions | Read private tables; write events; run crawlers or AI |
| Supabase | Storage, RLS, the `api` surface, migrations | Business logic beyond input constraints |

### Repository layout (target)

```text
/
├── apps/
│   ├── web/            Next.js public site (Vercel root directory)
│   └── admin/          Next.js local admin
├── services/
│   └── api/            FastAPI (uv project)
├── supabase/
│   ├── config.toml
│   ├── migrations/     the only schema source
│   ├── seed.sql        dev seed (generated from legacy events.json)
│   └── tests/          pgTAP tests (visibility + privilege rules)
├── docs/
├── legacy/             (at cutover) old static site kept for reference, then deleted
├── package.json        pnpm workspace root (scripts: dev, lint, typecheck, build)
├── pnpm-workspace.yaml
└── MASTER_PLAN.md
```

### Ports (local)

| Service | Port | Note |
|---|---|---|
| Public web (dev) | 3000 | Next.js default |
| Admin | 3001 | `next dev -p 3001 -H 127.0.0.1` |
| FastAPI | 8000 | `uvicorn --host 127.0.0.1` |
| Ollama | 11434 | Default; bound to localhost by default |
| Supabase local | 54321 (API), 54322 (DB), 54323 (Studio) | `supabase start` defaults |

Start command (M1): `pnpm dev`. It runs web, admin and API in parallel (the API via `uv run`). `supabase start` and Ollama are started separately because they are long-lived.

### Data flow: event lifecycle (V1)

```text
[manual create in admin] → draft ─► in_review ─► approved ─► published ─► archived
                                  └► rejected            (unpublish → approved)
publish:   FastAPI sets status=published, published_at → POST web /api/revalidate
telegram:  (V1.1) preview → sendPhoto(url=/events/<slug>/opengraph-image) → publications row
```

The public phase (Upcoming / Applications open / Closing soon / Past) is **computed from dates**. It is never stored, which keeps the existing site's sound principle.
