# Local Admin

Two processes on the developer laptop: **Admin UI** (`apps/admin`, Next.js) and **API** (`services/api`, FastAPI). Neither is exposed to the network.

## 1. Admin UI (`apps/admin`)

- Next.js 16 + TypeScript + Tailwind + shadcn/ui, **starting from the official `dashboard-01` block** (`pnpm dlx shadcn@latest add dashboard-01`). We do not redesign it.
- Geist font, Lucide icons (both are shadcn defaults).
- Runs `next dev -p 3001 -H 127.0.0.1` (dev) or `next start -p 3001 -H 127.0.0.1`.
- All data access happens **server-side** (Server Components / Server Actions) through a small typed client for FastAPI. Types are generated from FastAPI's OpenAPI with `openapi-typescript`. The browser never talks to FastAPI.
- Env (`apps/admin/.env.local`): `ADMIN_API_URL=http://127.0.0.1:8000`, `ADMIN_API_TOKEN=<random 32 bytes>`; optional `ADMIN_ALLOWED_HOSTS` (default `127.0.0.1,localhost`, see SECURITY §4). Nothing else.

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
- `src/proxy.ts` rejects (400) any request whose Host / X-Forwarded-Host / Origin is not an allowed admin host (DNS rebinding, SECURITY §4).
- Row actions and buttons come from the event's `allowed_actions`. Publish, reject, request changes, unpublish and archive open a confirmation dialog (reason required for reject, optional for request changes); approve, submit and reopen are one click. A 409 is shown inline and the page is re-rendered so the offered actions match the current status. Focus returns to the action buttons after a dialog closes or an action completes, and to the first invalid field (or the error message) after a failed form submit.
- The edit form PATCHes only the fields that changed (textarea CRLF line breaks are normalized to LF before comparing and sending), so an unchanged save does not bump `updated_at` or revalidate the public site.
- Lists: `?page=` above 10 000 or not a plain number falls back to 1; a page past the end redirects to the last page.
- Timestamps are shown in Europe/Istanbul; event dates as stored (YYYY-MM-DD).
- Header health dots: API (`/health`) and DB (`/system/db`) on every page; Ollama and Telegram results are reused for 5 minutes (the Ollama check runs a test generation). Settings always runs them fresh, sharing a check that is still running, so one page load starts at most one test generation. The Telegram card lists missing, missing optional and unneeded (excess) rights.
- Unit tests (`pnpm --filter admin run test`, vitest) cover the pure helpers: host allow-list, error mapping, form ⇄ payload conversion and diffing (incl. CRLF), source payload, health levels, paging, date formatting, URL safety.

## 2. API (`services/api`)

- Python 3.12+, `uv` project, FastAPI, Pydantic v2, pydantic-settings, psycopg 3 (`psycopg[binary,pool]`), httpx2 (runtime, D-20).
- Runs `uv run uvicorn fhc_api.main:create_app_from_env --factory --host 127.0.0.1 --port 8000` (via `pnpm dev`). `create_app(settings)` is the factory used by tests.
- Middleware: `TrustedHostMiddleware(allowed_hosts=ALLOWED_HOSTS)` (default `["127.0.0.1","localhost"]`; foreign `Host` → 400), bearer-token dependency (`hmac.compare_digest`) on every route except `/health` (missing/wrong → 401). No CORS middleware (no browser caller).
- No Swagger UI. The OpenAPI schema is served at `GET /openapi.json` **with the bearer token** (M4 generates TypeScript types from it). Every operation has an explicit snake_case `operationId` and documented error responses.
- Sync endpoints + a sync `psycopg_pool.ConnectionPool` (autocommit connections; every write runs in an explicit `conn.transaction()` in the service, so it has committed before revalidation runs as a background task). The pool opens with `wait=False`: the API starts and `/health` answers when the DB is down; DB routes then return 503.
- Errors are always `{"detail": ...}`: a string for API rules (404, 409, 422, 503), FastAPI's list of field errors for request validation (422). Postgres errors are mapped by class (unique → 409, check/FK → 422 with the constraint name, connection → 503) and are never echoed or logged verbatim (their messages can contain row values / personal data). A `pydantic.ValidationError` raised inside a handler (e.g. a row that no longer matches its response model) is a generic 500 `{"detail": "internal error"}`; only the error types and field locations are logged, never input values.

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
| `GET /llm/check` | `llm_check` | Provider health (`ok`, `not_running`, `model_missing`, `error`) plus one schema-constrained test call when healthy. A rejected `OLLAMA_*` configuration (e.g. a non-local URL) does not stop the API: health is `error` with the configuration message |
| `GET /telegram/check` | `telegram_check` | `getMe` + `getChat` + `getChatMember`; status `not_configured`, `invalid_token` (also for a malformed `TELEGRAM_BOT_TOKEN`, which does not stop the API), `chat_not_found`, `bot_not_admin`, `missing_rights`, `ok` or `error`; plus `missing_rights`, `missing_optional_rights` (delete, information only) and `excess_rights` (rights V1 does not need, warning only) |
| `GET /admin-bot/status` | `admin_bot_status` | Telegram admin bot (V1.1b): `enabled`, `state` (`disabled`, `config_error`, `stopped`, `starting`, `running`, `error`), `running`, `config_error`, `bot_username`, `allowlist_size`, `max_press_age_hours`, `scan_interval_seconds`, `last_poll_at`, `last_scan_at`, `last_error(_at)`, `pending_notifications`, `pending_replies`. No Telegram call; never contains the token |
| `GET /openapi.json` | (not in the schema) | The OpenAPI schema; requires the token like every other route |

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
├── telegram/            client.py (httpx2), check.py, formatting.py, router.py (V1: /telegram/check)   [M6]
├── llm/                 provider.py (Protocol), ollama.py, untrusted.py, router.py (V1: /llm/check)   [M6]
├── admin_bot/           settings, codec, messages, store, outbox, handlers, runner, bot, router,
│                        whoami (Telegram admin decisions)                                          [V1.1b]
├── overview/            router.py (counters + heartbeats)
├── system/              router.py (/system/db)
└── web/                 revalidate.py (POST to public site, best effort)
```

### Safe fetcher (`common/http.py`)

Implements CRAWLING_RESEARCH §5 for every hop: http/https only, ports 80/443, no credentials in URLs; DNS resolved by the API and the request refused if **any** address is not globally routable (private, loopback, link-local/metadata, ULA, CGNAT, multicast, deprecated site-local, and IPv6 forms that embed an IPv4 address: IPv4-mapped, -compatible and -translated are blocked, NAT64 `64:ff9b::/96` is judged by its embedded IPv4 address); the connection is pinned to the checked address (original host in `Host` and TLS SNI, so no second lookup can be rebound); environment proxies ignored; manual redirects (max 5, re-checked); 10 s timeouts; when a body is read, a 5 MB streamed cap and an HTML/JSON/XML/image content-type allow-list. Known gaps: no timeout on the OS DNS lookup and no overall wall-clock limit across hops.

### Review signals (`review/signals.py`)

Each signal is `{key, status: pass|warn|fail|info, detail, blocks_approval}`; no scores. Official URL reachable = headers-only GET through the safe fetcher, final 2xx/3xx (an invalid/non-public URL fails and blocks approval, and is never fetched). The endpoint finishes its database reads and returns the pooled connection before the fetch. Dates coherent = `start ≤ end` and `deadline ≤ end_date` (or `≤ start_date` when there is no end date). Possible duplicate = same `official_url_normalized`, or same `fold_title(title)` + same start date.

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
- `publish` sets `published_at = now()`; `archive` sets `archived_at`; `reopen` clears `archived_at` but keeps the old `published_at` (a later `publish` overwrites it).
- `POST /events` retries a lost slug race (a concurrent create took the chosen slug between the check and the insert) with the next free slug, up to 3 attempts in savepoints; after that it returns the usual 409.
- Revalidation (tags `events`, `event:<slug>`) runs whenever the event enters or leaves `published` (publish, unpublish, archive from published) and on edits of a published event. It is best effort: failures are logged (status code or exception class only) and never fail the request; it is disabled when `WEB_BASE_URL` or `WEB_REVALIDATE_SECRET` is unset.

### Env (`services/api/.env`, gitignored; names in `services/api/.env.example`)

`DATABASE_URL` and `ADMIN_API_TOKEN` (≥ 32 chars) are required; empty values count as unset; unknown keys are ignored (the file is shared with the M6 modules). Tests never read `.env`: they use `TEST_DATABASE_URL` or the local default and refuse non-local hosts.

```text
DATABASE_URL=postgresql://admin_backend:...@<pooler-host>:5432/postgres?sslmode=require
ADMIN_API_TOKEN=...
WEB_BASE_URL=https://<public-site>
WEB_REVALIDATE_SECRET=...
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:0.8b        # default; placeholder until the V1.2 benchmark
TELEGRAM_BOT_TOKEN=              # optional in V1
TELEGRAM_CHANNEL_ID=             # optional in V1
TELEGRAM_ADMIN_ENABLED=false     # V1.1b admin bot; default false
TELEGRAM_ADMIN_BOT_TOKEN=        # a separate bot (not TELEGRAM_BOT_TOKEN)
TELEGRAM_ADMIN_USER_IDS=         # numeric ids, comma-separated (whoami helper)
TELEGRAM_ADMIN_MAX_PRESS_AGE_H=12
TELEGRAM_ADMIN_SCAN_INTERVAL_S=60
```

The `TELEGRAM_ADMIN_*` values are read as raw strings and parsed by `admin_bot/settings.py`, so a bad value (unknown boolean, empty or non-numeric allowlist, out-of-range number, malformed token, the channel bot's token) only disables the bot and is reported by `GET /admin-bot/status`; the API starts normally.

### Telegram admin bot (V1.1b, as built)

Plan: `docs/planning/V1_1B_TELEGRAM_ADMIN.md` (D-21). Only the private chat with the separate admin bot is used.

- **Lifecycle.** `AdminBot` is built by `create_app`; when enabled and valid, the lifespan starts one daemon thread (`fhc-admin-bot`) and stops it first on shutdown (before the Telegram client and the pool close). Loop: `getMe` once, then an outbox scan whenever due (or requested after an action), then `getUpdates` (`timeout` ≤ 10 s, `allowed_updates=["message","callback_query"]`, persisted `offset`). Any failure is logged without secrets or personal data, shown in the status, and followed by exponential backoff (2 s … 300 s; `retry_after` on 429; 10 min after `getMe` 401/404). Malformed updates are skipped (only their id is kept and confirmed). An update whose handling fails with a database *connection* error is not confirmed and is retried after the backoff, at most 5 times; any other error (e.g. a cancelled statement) is logged and the update confirmed. Shutdown: the stop flag ends backoff and pacing waits at once and is checked between updates, sends and edits, so the thread stops after the call in progress (long poll ≤ 20 s HTTP timeout, other Bot API calls ≤ 10 s, pool checkout ≤ 10 s, statements ≤ 15 s); `stop()` waits at most 25 s, then logs a warning and leaves the daemon thread to exit. Normally shutdown takes well under a second. The handler commits before the offset is saved: a crash in between re-processes that update after a restart, which is harmless except that a Request changes / Confirm reject press can send a second reason prompt.
- **Connections.** Every unit of work takes a short pool checkout; no connection is held during a Telegram call or the long poll.
- **Outbox** (`outbox.py`). Each scan retires live messages by editing them without buttons: `superseded` when their entity changed (status/`updated_at` changed, decided in the admin UI, deleted), `expired` when unpressed for longer than `TELEGRAM_ADMIN_MAX_PRESS_AGE_H` (a fresh message follows in the same scan, so a pending decision is re-sent about every 12 h). It then sends one message per missing slot: events in `in_review` (review: Approve / Request changes / Reject, with the deterministic review signals, no network URL check), `approved` events (publish prompt: Publish / Later), `new` community and team applications (Contacted / Accepted / Declined / Spam). A slot `(entity, kind, state token, admin chat)` is claimed in `app.bot_notifications` before `sendMessage` (partial unique index, `ON CONFLICT DO NOTHING`), so restarts and concurrent scans never send it twice; a failed send releases the claim (a lost response after a successful send can cause one duplicate on retry); a claim left by a crash is freed after 10 min. At most 10 entities get new messages per candidate list (review events, publish events, community applications, team applications) and scan, 1 s apart; a chat that answered 403 is skipped for 15 min.
- **Buttons** (`codec.py`). `callback_data = v1:<action>:<e|c|t>:<id 32 hex>:<token 8 hex>` (≤ 50 bytes). Token: first 8 hex of SHA-256 of the entity's `updated_at` (the migration adds `updated_at` and its trigger to both application tables), so an application set back to `new` is notified again.
- **Presses** (`handlers.py`). Allowlist by numeric user id and chat id = user id (private); strangers get "Not allowed." and a content-free log line (warning at most once per 10 min, then debug); messages from strangers get no reply. Then the message must be a live notification of this bot (looked up by chat and message id, row locked), the button's token must match it, its age (`sent_at`, DB clock) must be ≤ `TELEGRAM_ADMIN_MAX_PRESS_AGE_H` (otherwise it is marked `expired` and the next scan sends a fresh message), and the token must match the entity as it is now (row locked; otherwise "Outdated", marked `superseded`). Actions run through `events.service.transition_event` / `community.service.set_status` in the same transaction (same guards, notes, timestamps, 409/422 answers). Publish and Reject replace the buttons with Confirm / Cancel and record the stage on the notification (`confirm_action`, `confirm_at`); a Confirm press is accepted only for the recorded action within 10 min (a crafted Confirm without the first press is refused); Cancel clears it. A press on an already resolved message also removes its buttons. Reject (after confirm) and Request changes send a `force_reply` prompt; the reply (1–1000 characters, as a reply to that prompt in the same chat) executes the action with the reason. A reply has no press-age check of its own: the 15-min prompt TTL and the state token bound it. A refused reason keeps the prompt open. After commit: answer the press, edit every admin's message for that entity to the outcome, revalidate the public site when the event enters or leaves `published` (best effort), request a scan (e.g. the publish prompt after Approve).
- **Audit.** `app.admin_actions` gets one row per executed transition and application status change, from the admin UI (`admin_ui`) and Telegram (`telegram:<user id>`), in the same transaction as the change. `detail` holds `from`/`to` (and whether a reason was given), never text or personal data.
- **Personal data.** Application messages carry the type, the first name and the chosen channel only.
- **`whoami`.** `uv run python -m fhc_api.admin_bot.whoami` (API stopped or bot disabled) prints the numeric ids of users who messaged the bot; it does not confirm updates.
- **Tests.** Unit (codec, config, messages, client additions, redaction), integration with a fake Bot API (MockTransport) and rolled-back transactions (`test_admin_bot_flow.py`), wiring/lifespan and an end-to-end run of the real thread (`test_admin_bot_app.py`), audit (`test_admin_audit.py`), pgTAP `04_admin_bot.test.sql`.
- **Known limits.** Telegram keeps undelivered updates for 24 h; presses made while the API is off longer than that are lost. `app.bot_notifications` and `app.admin_actions` are not pruned (small, no personal data). Exactly one API process may run with the bot enabled (a second poller gets 409 and reports it).
- **Settings card.** "Telegram admin bot" shows the state, configuration or last error, bot, allowlist size, last poll/scan and pending counts.

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

### Known limitations (V1, deferred)

- The safe fetcher connects only to the first resolved address (all addresses are checked, but there is no fallback to the next one when the first is unreachable).
- The 5 MB body cap is counted per decoded chunk, so one highly compressed chunk can decode to more than the cap before the check runs. `read_body=True` is unused in V1 (the review check reads headers only).
- FastAPI validates request bodies before the auth dependency runs: an unauthenticated malformed POST gets 422 (field errors, no data), and an unknown path gets 404, instead of 401.
- The app's INFO logs (e.g. "web revalidation enabled") are not shown under uvicorn's default logging configuration; warnings and errors are.

## 3. Local development

1. `pnpm install` (root), `uv sync` (in `services/api`)
2. `pnpm supabase start` (Docker; local Postgres + Data API + Studio), then `pnpm supabase db reset` (migrations + seed)
3. `ollama serve` (optional in V1)
4. `pnpm dev` → web :3000, admin :3001, api :8000

Docker is required only for the local Supabase stack. Against the cloud project, Docker is not needed.
