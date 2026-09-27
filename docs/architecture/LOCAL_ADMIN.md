# Local Admin

Two processes on the developer laptop: **Admin UI** (`apps/admin`, Next.js) and **API** (`services/api`, FastAPI). Neither is exposed to the network.

## 1. Admin UI (`apps/admin`)

- Next.js 16 + TypeScript + Tailwind + shadcn/ui, **starting from the official `dashboard-01` block** (`pnpm dlx shadcn@latest add dashboard-01`). We do not redesign it.
- Geist font, Lucide icons (both are shadcn defaults).
- Runs `next dev -p 3001 -H 127.0.0.1` (dev) or `next start -p 3001 -H 127.0.0.1`.
- All data access happens **server-side** (Server Components / Server Actions) through a small typed client for FastAPI. Types are generated from FastAPI's OpenAPI with `openapi-typescript`. The browser never talks to FastAPI.
- Env (`apps/admin/.env.local`): `ADMIN_API_URL=http://127.0.0.1:8000`, `ADMIN_API_TOKEN=<random 32 bytes>`. Nothing else.

### dashboard-01 adaptation

| dashboard-01 part | Becomes |
|---|---|
| `AppSidebar` | Navigation below |
| `SectionCards` | Overview counters: *In review*, *Published (upcoming)*, *Closing in 7 days*, *New community applications*. Each links to a filtered list |
| `ChartAreaInteractive` | **Removed in V1.** V1.4 may replace it with a "discoveries per day by outcome" bar once discovery exists |
| `DataTable` | Events table (title, status, verification, start, deadline, updated). The row drag handle is removed. Row actions: edit, submit for review, publish/unpublish, archive |
| `SiteHeader` | Page title + breadcrumbs + health indicator (API/DB/Ollama/Telegram dots) |

### Navigation

| Section | V1 | Later |
|---|---|---|
| Overview | ✔ | |
| Events (list, create, edit) | ✔ | |
| Review | ✔ (manual checks) | V1.2 evidence view |
| Discovery | placeholder hidden | V1.2 URL import, V1.4 sources |
| Publishing → Telegram | settings check only | V1.1 preview + send + history |
| Community Applications | ✔ read + status change | |
| Contributions (team applications) | ✔ read + status change | |
| Sources | ✔ simple list/edit | |
| Runs | hidden | V1.2 |
| Settings | ✔ connection tests (DB, Ollama, Telegram, web revalidate) | |

Instagram and WhatsApp sections are **not** created.

### Review screen (V1 scope)

Two columns: **Event data** (left) and **Evidence** (right). In V1, evidence is the list of `event_sources` plus deterministic signals computed by the API:

| Signal | Rule (deterministic) |
|---|---|
| Official URL reachable | `HEAD`/`GET` → 2xx/3xx (through the safe fetcher) |
| Registration URL present | `application_url` not null |
| Dates coherent | `deadline ≤ end_date`, `start ≤ end` |
| Deadline missing | `application_deadline` null |
| Deadline passed | deadline < today (in the event timezone) |
| Possible duplicate | same `official_url_normalized`, or same normalized title + start date |
| Supporting sources | count of `event_sources` by tier |

No LLM confidence percentages are shown, now or later.

## 2. API (`services/api`)

- Python 3.12+, `uv` project, FastAPI, Pydantic v2, pydantic-settings, psycopg 3 (pool), httpx.
- Runs `uv run uvicorn fhc_api.main:app --host 127.0.0.1 --port 8000` (via `pnpm dev`).
- Middleware: `TrustedHostMiddleware(allowed_hosts=["127.0.0.1","localhost"])`, bearer-token dependency on every route except `/health`. No CORS middleware (no browser caller).

### Module layout

```text
services/api/src/fhc_api/   (uv packaged layout; tests in services/api/tests/)
├── main.py              app factory, middleware, routers
├── config.py            Settings (pydantic-settings, reads .env)
├── db.py                pool + transaction helper
├── security.py          token check
├── common/              normalize.py (slug, url, turkish folding), clock.py (today in tz), http.py (safe fetcher)
├── events/              models.py, repository.py, service.py (state machine), router.py
├── sources/             models, repository, router
├── review/              signals.py (deterministic checks), router.py
├── community/           models, repository, router (read + status update)
├── publishing/          hashing.py (publishable projection + sha256), models.py
│   └── telegram/        client.py (httpx), router.py (V1: /telegram/check)
├── llm/                 provider.py (Protocol), ollama.py, router.py (V1: /llm/check)
└── web/                 revalidate.py (POST to public site)
```

Modules added later: `discovery/`, `crawling/`, `extraction/`, `verification/`, `deduplication/`, `runs/`. These are folders, not services.

### State machine (events/service.py)

| From | Action | To | Guard |
|---|---|---|---|
| draft | submit | in_review | required fields present |
| in_review | approve | approved | no failing hard checks (dates coherent, official URL valid) |
| in_review | reject | rejected | reason stored in `internal_notes` |
| in_review | request changes | draft | |
| approved | publish | published | sets `published_at`, triggers revalidation |
| published | unpublish | approved | triggers revalidation |
| published / approved | archive | archived | |
| rejected / archived | reopen | draft | |

Editing a published event keeps it published, triggers revalidation, and marks "changed since published" for Telegram (V1.1).

### Env (`services/api/.env`, gitignored)

```text
DATABASE_URL=postgresql://admin_backend:...@<pooler-host>:5432/postgres?sslmode=require
ADMIN_API_TOKEN=...
WEB_BASE_URL=https://<public-site>
WEB_REVALIDATE_SECRET=...
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b          # placeholder until benchmark
TELEGRAM_BOT_TOKEN=              # optional in V1
TELEGRAM_CHANNEL_ID=             # optional in V1
```

## 3. Local development

1. `pnpm install` (root), `uv sync` (in `services/api`)
2. `pnpm supabase start` (Docker; local Postgres + Data API + Studio), then `pnpm supabase db reset` (migrations + seed)
3. `ollama serve` (optional in V1)
4. `pnpm dev` → web :3000, admin :3001, api :8000

Docker is required only for the local Supabase stack. Against the cloud project, Docker is not needed.
