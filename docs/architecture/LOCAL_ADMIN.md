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

### As built (M4)

| Route | Shows |
|---|---|
| `/` | Overview: four counters (link to filtered lists), keep-alive heartbeats (red "Stale" when the API marks a source stale), 10 most recently updated events |
| `/events` | Events table; filters by status, *Upcoming (published)* (`?view=upcoming`), *Closing in 7 days* (`?view=closing`); 25 per page (`?page=`) |
| `/events/new`, `/events/[id]` | Create (draft) and edit forms with every `EventUpdate` field; status, timestamps and the allowed actions above the edit form |
| `/events/[id]/review` | Event data \| Evidence (review signals, duplicates, sources by tier, event sources with add/remove) |
| `/review` | Review queue (events in review) |
| `/community-applications`, `/contributions` | Application tables with status filter, paging and a status select + Save per row |
| `/sources`, `/sources/new`, `/sources/[id]` | Source list, create, edit (the API has no `GET /sources/{id}`; the edit page reads the list) |
| `/settings` | DB, Ollama (health + test output and latency) and Telegram checks, each streamed separately; web revalidation is shown as "not reported" because the API does not expose it |

- `src/lib/api/client.ts` (`server-only`) is the only place that reads `ADMIN_API_URL` / `ADMIN_API_TOKEN`. Every call returns `{ok, data} | {ok: false, error}`; errors carry an English message (unreachable, timeout, 401, 404, 409, 422 with per-field messages, 503). Pages render that state instead of throwing. Bodies are never logged.
- `src/lib/api/schema.ts` is generated: `pnpm --filter admin run api:types` with the API running and the token in `apps/admin/.env.local` (the script fetches `/openapi.json` with the bearer token and runs openapi-typescript's Node API, because its CLI cannot send headers).
- Row actions and buttons come from the event's `allowed_actions`. Reject, request changes, unpublish and archive open a dialog (reason required for reject, optional for request changes). A 409 is shown inline and the page is re-rendered so the offered actions match the current status.
- The edit form PATCHes only the fields that changed, so an unchanged save does not bump `updated_at` or revalidate the public site.
- Header health dots: API (`/health`) and DB (`/system/db`) on every page; Ollama and Telegram results are reused for 5 minutes (the Ollama check runs a test generation). Settings always runs them fresh.
- Unit tests (`pnpm --filter admin run test`, vitest) cover the pure helpers: error mapping, form ⇄ payload conversion and diffing, health levels, paging, URL safety.

## 2. API (`services/api`)

- Python 3.12+, `uv` project, FastAPI, Pydantic v2, pydantic-settings, psycopg 3 (`psycopg[binary,pool]`), httpx2 (runtime, D-20).
- Runs `uv run uvicorn fhc_api.main:create_app_from_env --factory --host 127.0.0.1 --port 8000` (via `pnpm dev`). `create_app(settings)` is the factory used by tests.
- Middleware: `TrustedHostMiddleware(allowed_hosts=ALLOWED_HOSTS)` (default `["127.0.0.1","localhost"]`; foreign `Host` → 400), bearer-token dependency (`hmac.compare_digest`) on every route except `/health` (missing/wrong → 401). No CORS middleware (no browser caller).
- No Swagger UI. The OpenAPI schema is served at `GET /openapi.json` **with the bearer token** (M4 generates TypeScript types from it). Every operation has an explicit snake_case `operationId` and documented error responses.
- Sync endpoints + a sync `psycopg_pool.ConnectionPool` (autocommit connections; every write runs in an explicit `conn.transaction()` in the service, so it has committed before revalidation runs as a background task). The pool opens with `wait=False`: the API starts and `/health` answers when the DB is down; DB routes then return 503.
- Errors are always `{"detail": ...}`: a string for API rules (404, 409, 422, 503), FastAPI's list of field errors for request validation (422). Postgres errors are mapped by class (unique → 409, check/FK → 422 with the constraint name, connection → 503) and are never echoed or logged verbatim (their messages can contain row values / personal data).

### Endpoints

All require `Authorization: Bearer <ADMIN_API_TOKEN>` except `/health`.

| Method + path | operationId | Notes |
|---|---|---|
| `GET /health` | `health` | Unauthenticated |
| `GET /overview` | `get_overview` | `in_review`, `published_upcoming` (last day ≥ today), `closing_within_7_days` (published, deadline today..today+7), `new_community_applications`, `new_team_applications`, `heartbeats` (both sources, `stale` when never seen or > 48 h). "Today" is per event timezone |
| `GET /events` | `list_events` | `status` (repeatable), `upcoming`, `closing_within_days`, `limit` (1–200, default 50), `offset` → `{items,total,limit,offset}` ordered by `updated_at desc` |
| `POST /events` | `create_event` | Creates a `draft`; slug from title (`slugify`, `-2`, `-3`… on collision, ≤ 80); `official_url_normalized` via `normalize_url` |
| `GET /events/{id}` | `get_event` | Includes `allowed_actions` (from the state machine) |
| `PATCH /events/{id}` | `update_event` | Partial; `null` clears optional fields. Slug never changes. Approved/published events must keep passing the approval checks (422). Editing a published event revalidates |
| `POST /events/{id}/transitions` | `transition_event` | Body `{action, reason?}`; see state machine |
| `GET /events/{id}/review` | `get_event_review` | Signals + duplicates + sources by tier; `check_url=false` skips the network check |
| `GET/POST /events/{id}/sources` | `list_event_sources`, `add_event_source` | `url_normalized` via `normalize_url`; same normalized URL twice → 409 |
| `DELETE /events/{id}/sources/{event_source_id}` | `remove_event_source` | 204 |
| `GET/POST /sources`, `PATCH /sources/{id}` | `list_sources`, `create_source`, `update_source` | |
| `GET /community-applications`, `PATCH /community-applications/{id}` | `list_community_applications`, `update_community_application` | Personal data: authenticated only, never logged. PATCH body `{status}` |
| `GET /team-applications`, `PATCH /team-applications/{id}` | `list_team_applications`, `update_team_application` | Same |
| `GET /system/db` | `check_database` | `{ok, latency_ms, role, server_version}`; 503 when the DB is unreachable |

### Module layout

```text
services/api/src/fhc_api/   (uv packaged layout; tests in services/api/tests/)
├── main.py              app factory, middleware, routers
├── config.py            Settings (pydantic-settings, reads services/api/.env)
├── db.py                pool + per-request connection dependency
├── security.py          token check
├── common/              normalize.py (slug, url, Turkish folding, title key), clock.py (today in tz),
│                        http.py (safe fetcher), fields.py (shared field types), models.py (PATCH base),
│                        pagination.py, sql.py (insert/update/page helpers), errors.py
├── events/              models.py, repository.py, service.py (state machine), router.py
├── sources/             models, repository, router (sources + event sources)
├── review/              models.py, signals.py (deterministic checks), router.py
├── community/           models, repository, router (read + status update)
├── publishing/          hashing.py (publishable projection + sha256)
│   └── telegram/        client.py (httpx2), router.py (V1: /telegram/check)   [M6]
├── llm/                 provider.py (Protocol), ollama.py, router.py (V1: /llm/check)   [M6]
├── overview/            router.py (counters + heartbeats)
├── system/              router.py (/system/db)
└── web/                 revalidate.py (POST to public site, best effort)
```

### Safe fetcher (`common/http.py`)

Implements CRAWLING_RESEARCH §5 for every hop: http/https only, ports 80/443, no credentials in URLs; DNS resolved by the API and the request refused if **any** address is not globally routable (private, loopback, link-local/metadata, ULA, CGNAT, multicast, IPv4-mapped forms); the connection is pinned to the checked address (original host in `Host` and TLS SNI, so no second lookup can be rebound); environment proxies ignored; manual redirects (max 5, re-checked); 10 s timeouts; when a body is read, a 5 MB streamed cap and an HTML/JSON/XML/image content-type allow-list. Known gaps: no timeout on the OS DNS lookup and no overall wall-clock limit across hops.

### Review signals (`review/signals.py`)

Each signal is `{key, status: pass|warn|fail|info, detail, blocks_approval}`; no scores. Official URL reachable = headers-only GET through the safe fetcher, final 2xx/3xx (an invalid/non-public URL fails and blocks approval). Dates coherent = `start ≤ end` and `deadline ≤ end_date` (or `≤ start_date` when there is no end date). Possible duplicate = same `official_url_normalized`, or same `fold_title(title)` + same start date.

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

As built (M3):
- Invalid transition (wrong source status) → 409 `cannot <action> an event in status <status>`. A failing guard → 409 `cannot <action>: <problems>`.
- "Required fields" = `title`, `summary`, `official_url`, `start_date`, `format`. Approve **and publish** check required fields + dates coherent + official URL valid (http/https, port 80/443, public fully qualified host; static, no network).
- `reject` needs `reason` (422 otherwise). Any given `reason` is appended to `internal_notes` as `[<UTC time>] <action>: <reason>`.
- `publish` sets `published_at = now()`; `archive` sets `archived_at`; `reopen` clears `archived_at`. Revalidation (tags `events`, `event:<slug>`) runs whenever the event enters or leaves `published` (publish, unpublish, archive from published) and on edits of a published event. It is best effort: failures are logged (status code or exception class only) and never fail the request; it is disabled when `WEB_BASE_URL` or `WEB_REVALIDATE_SECRET` is unset.

### Env (`services/api/.env`, gitignored; names in `services/api/.env.example`)

`DATABASE_URL` and `ADMIN_API_TOKEN` (≥ 32 chars) are required; empty values count as unset; unknown keys are ignored (the file is shared with the M6 modules). Tests never read `.env`: they use `TEST_DATABASE_URL` or the local default and refuse non-local hosts.

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

### Database role `admin_backend`

Migrations create the role as `NOLOGIN`, with RLS policies granting it full access to `app.*`. Login is enabled per environment, outside migrations:

- **Local:** `pnpm db:start` / `pnpm db:reset` run `pnpm db:local-login`, which sets the password `admin_backend_local_dev` **inside the local Docker container only**. It is deliberately not a seed file, because `supabase db push --include-seed` would run seed files against the cloud. Connection string: `postgresql://admin_backend:admin_backend_local_dev@127.0.0.1:54322/postgres`.
- **Cloud (M7):** run once in the SQL editor with a generated password: `alter role admin_backend with login password '<generated>';`. Connect through the session pooler as user `admin_backend.<project-ref>`. Whether the pooler accepts a custom role must be verified at M7.

### Database scripts (repo root)

| Script | Does |
|---|---|
| `pnpm db:start` / `pnpm db:stop` | Start or stop the local Supabase stack (Docker) |
| `pnpm db:reset` | Recreate the local DB: migrations + `seed_legacy_events.sql`, then `db:local-login` |
| `pnpm test:db` | pgTAP tests in `supabase/tests/database/` |
| `pnpm db:types` | Regenerate `apps/web/src/lib/database.types.ts` from the `api` schema |
| `pnpm db:legacy-seed` | Regenerate `supabase/seed_legacy_events.sql` from `events.json` (deterministic) |

Stop the stack when you are not developing (`pnpm db:stop`). Its ports listen on all interfaces (SECURITY S8).

## 3. Local development

1. `pnpm install` (root), `uv sync` (in `services/api`)
2. `pnpm supabase start` (Docker; local Postgres + Data API + Studio), then `pnpm supabase db reset` (migrations + seed)
3. `ollama serve` (optional in V1)
4. `pnpm dev` → web :3000, admin :3001, api :8000

Docker is required only for the local Supabase stack. Against the cloud project, Docker is not needed.
