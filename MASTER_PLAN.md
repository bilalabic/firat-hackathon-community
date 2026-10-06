# Master Plan: Fırat Hackathon Community

Last updated: 2026-09-28 · Current phase: **Planning complete. All decisions accepted. Next: M0 (waiting for the owner's go-ahead).**

## Product loop

```text
Discover → Verify → Structure → Review → Publish → Archive
```

## Documents

| Area | Document |
|---|---|
| Current repo | [docs/research/EXISTING_REPOSITORY.md](docs/research/EXISTING_REPOSITORY.md) |
| Architecture | [SYSTEM_ARCHITECTURE](docs/architecture/SYSTEM_ARCHITECTURE.md) · [DATA_MODEL](docs/architecture/DATA_MODEL.md) · [LOCAL_ADMIN](docs/architecture/LOCAL_ADMIN.md) · [PUBLIC_WEB](docs/architecture/PUBLIC_WEB.md) · [AI_ARCHITECTURE](docs/architecture/AI_ARCHITECTURE.md) · [SECURITY](docs/architecture/SECURITY.md) |
| Research | [STACK](docs/research/STACK_RESEARCH.md) · [LOCAL_LLM](docs/research/LOCAL_LLM_RESEARCH.md) · [CRAWLING](docs/research/CRAWLING_RESEARCH.md) · [TELEGRAM](docs/research/TELEGRAM_RESEARCH.md) |
| Planning | [MVP](docs/planning/MVP.md) · [ROADMAP](docs/planning/ROADMAP.md) · [DECISIONS](docs/planning/DECISIONS.md) · [RISKS](docs/planning/RISKS.md) · [OPEN_QUESTIONS](docs/planning/OPEN_QUESTIONS.md) |

## Versions

V1 Foundation → V1.1 Telegram publishing → V1.2 URL import + extraction → V1.3 Dedup + history → V1.4 Curated discovery → V1.5 Scheduling → V2 Public/community growth. See [ROADMAP](docs/planning/ROADMAP.md).

## V1 milestones

Every milestone follows the same steps: objective → inspect → implement → test → lint/typecheck → manual check → **Review 1 (functional)** → **Review 2 (engineering)** → fix → document. A milestone is closed only when both reviews are recorded in its log entry below.

| # | Milestone | Deliverables | Done when |
|---|---|---|---|
| **M0** | Repository hygiene | `.gitignore`; `deploy-pages.yml` uploads only the 4 legacy files via `_site/`; README note that a migration is in progress | Pages still deploys (check live URL + `events.json`); the artifact contains only 4 files |
| **M1** | Monorepo scaffold | `pnpm-workspace.yaml`, root scripts; `apps/web` and `apps/admin` (`create-next-app` + `shadcn init -t next`); `services/api` (`uv init`, FastAPI, ruff, mypy, pytest); `/health` endpoints; `pnpm dev` | MVP criteria 2–3 pass on empty apps |
| **M2** | Database | `supabase init`; migrations: schemas, enums, tables, RLS, default-privilege revoke, `admin_backend` role, `api` view + submit functions + `keep_alive` / `app.heartbeats`; seed generated from `events.json`; pgTAP tests | MVP 4–6, 18 pass locally |
| **M3** | API core | settings, DB pool, security middleware, `common/normalize` (ported slug/URL/Turkish folding with tests), events CRUD + state machine, sources, event_sources, review signals, applications read/update, web revalidation client, publishable hash | MVP 7, 9 (API side) pass in pytest |
| **M4** | Admin UI | `dashboard-01` adapted: Overview cards, Events table + form, Review (data vs evidence), Community Applications, Contributions, Sources, Settings | MVP 9–10 manual pass |
| **M5** | Public web | Routes, phase logic + tests, detail SEO/JSON-LD, OG card, community + team forms (Server Actions → RPC), sitemap/robots, `/api/revalidate`, `/api/cron/keep-alive` + `vercel.json` cron; Turkish UI copy in `lib/copy.ts` | MVP 12 (local), 14–17 |
| **M6** | Integration checks | `llm/` Ollama provider + `/llm/check`; `telegram/client.py` + `/telegram/check`; Settings buttons | MVP 11 |
| **M7** | Cloud + cutover | Supabase cloud project + migrations; Vercel project (`apps/web`) with `CRON_SECRET`; GitHub Actions keep-alive workflow + `SUPABASE_PUBLISHABLE_KEY` secret; heartbeat on the admin Overview; final legacy import; Pages → redirect page; remove Issue Form workflow + template; README rewrite (English) | MVP 1, 8, 12–13, 19–21 on production |

Dependencies: M0 → M1 → M2 → M3 → {M4, M5} → M6 → M7. M4 and M5 can run in parallel after M3. M5 only needs M2 and can start early.

## Decisions

Accepted on 2026-09-28:
- **D-03**: Supabase Free, must not pause.
- **D-19**: redundant keep-alive (Vercel Cron + GitHub Actions + heartbeat).
- **D-11**: Telegram in V1.1, discovery in V1.4.
- **D-13**: native `uv` and Ollama on Windows.
- **D-18**: Turkish-first public UI; code, docs and admin in English.

All other decisions (D-01, D-02, D-04–D-10, D-12, D-14–D-17) were accepted on 2026-09-28. Deferred owner inputs are Q3, Q4, Q9 and Q13 (see OPEN_QUESTIONS). None of them blocks M0–M4.

Owner actions outside the code:
- Create the Telegram channel and bot before M6 (TELEGRAM_RESEARCH §4).
- Create the Supabase cloud project (region: Frankfurt recommended) at the start of M7. Creating it earlier is fine too, but then the GitHub Actions keep-alive must be enabled the same day, or the dev project may pause.
- Decide the domain (Q4) before M7.

## Milestone log

### M0 Repository hygiene (2026-09-28): done, verified in production (PR #6, Pages run 36356572537)

**Changes**
- `.gitignore` added (env files except `.env.example`, Node/Next, Python, Supabase CLI state, caches, `_site/`).
- `deploy-pages.yml`:
  - stages only `index.html`, `style.css`, `script.js`, `events.json` into `_site/` and uploads that;
  - checkout uses `persist-credentials: false`.
- README: migration notice.

**Checks run**
- `check-jsonschema` (GitHub workflow schema) on both workflows: pass.
- `zizmor --offline`:
  - `artipacked` (medium) fixed;
  - 4 × `unpinned-uses` remain. They existed before, are accepted as S5, and these workflows are removed at M7.
- Staging step simulated on a clean `git archive`: exactly 4 files.
  - Served locally: `/`, CSS, JS and `events.json` return 200 (6 events).
  - `README.md` and `.github/…` return 404.
- `.gitignore` probes:
  - `.env`, `.env.local` and `.env.production` at any depth are ignored.
  - `.env.example` at any depth is tracked.
  - No currently tracked file became ignored.

**Review 1 (functional):**
- Both triggers (`push`, `workflow_call` from `add-event`) use the same job.
- `persist-credentials: false` does not affect `add-event`, which pushes from its own job.
- Accepted limitation: a new legacy asset would need adding to the copy list. The legacy site is frozen.

**Review 2 (engineering):**
- Removed a redundant `.gitignore` negation.
- Staging via `cp` is the simplest option, because `upload-pages-artifact` has no include list.
- No new dependencies.

**Production check:** Pages run `success`.
- Live `/`, `style.css`, `script.js` and `events.json` return 200 (6 events).
- `/README.md`, `/MASTER_PLAN.md`, `/docs/…` and `/.github/…` return 404.

Note: a repo-local git identity (`user.name`, `user.email`, taken from earlier commits) was set, because no global identity exists on this machine.

### M1 Monorepo scaffold (2026-09-28): done locally

**Changes**
- pnpm workspace root (`apps/*`, `services/*`). Root scripts: `dev`, `lint`, `typecheck`, `test`, `build`. `allowBuilds` for `sharp` / `unrs-resolver` lives at the root.
- `apps/web`: `create-next-app` 16.3.6 (TS, Tailwind v4, ESLint, App Router, `src/`), shadcn init (base-nova, neutral, Lucide), `lang="tr"`, Geist with `latin-ext` (Turkish glyphs), placeholder home, `/api/health`.
- `apps/admin`: same base + official `dashboard-01` block, `TooltipProvider`, bound to `127.0.0.1:3001`, `/` → `/dashboard`, `noindex`, `/api/health`.
- `services/api`: `uv` packaged project `fhc_api` (Python 3.12), FastAPI + uvicorn, `/health` + test. Tooling: ruff (with `ı`/`İ` allowed as confusables), mypy strict, pytest. A `package.json` wrapper puts it into the pnpm scripts.
- Scaffold fixes:
  - removed per-app `.gitignore` (it ignored `.env.example`), per-app `pnpm-workspace.yaml`, template READMEs and template SVGs;
  - `typecheck` = `next typegen && tsc --noEmit` (the `LayoutProps` globals are generated);
  - fixed 2 `react-hooks/set-state-in-effect` lint errors in shadcn code (`use-mobile` → `useSyncExternalStore`; chart range switch computed during render).
- README development section. `LOCAL_ADMIN.md` updated to the `fhc_api` layout.

**Checks run**
- `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`: all exit 0.
  - Build: web routes `/`, `/api/health`; admin routes `/`, `/dashboard`, `/api/health`.
- `pnpm dev` smoke test:
  - web, admin and api health endpoints return 200; `/dashboard` 200; web `lang="tr"`.
  - Admin (3001) and API (8000) are **not** reachable on the LAN interface.
  - Ports are released after stop; no errors in the dev log.

**Review 1 (functional):**
- MVP criteria 2–3 are met on empty apps.
- Found and fixed: `.env.example` would have been ignored; typecheck failed on a clean checkout.

**Review 2 (engineering):**
- Removed the unused `pydantic-settings` (M3 adds it back when needed).
- No shared packages. No extra dependencies beyond the generators' defaults and shadcn's block dependencies.

**Open:**
- ~~Starlette `httpx` deprecation warning~~: resolved after M1 by switching to `httpx2` (owner-approved, D-20). pytest passes with `-W error`.
- Terminals opened before the `uv` install need a restart to find `uv`.

### M2 Database (2026-09-28): done locally

**Changes**
- Supabase CLI 2.118.0 as a root devDependency.
- `supabase/config.toml`:
  - Data API exposes only `api`;
  - realtime, storage, edge runtime and analytics are disabled locally;
  - auth signup is disabled.
- Migrations:
  - `20260928120000_core_schema.sql`: `app` schema, enums, 7 tables with constraints, RLS on all tables, `admin_backend` role (NOLOGIN, `statement_timeout` 15s) with policies and default grants. Also a **global** revoke of PUBLIC EXECUTE on future functions, and full revokes of Supabase's `public`-schema default grants.
  - `20260928120100_public_api.sql`: `api.events_public` view, `submit_community_application`, `submit_team_application` and `keep_alive` (all security definer, empty `search_path`, generic `22023` errors), plus private payload helpers in `app`.
- Seed: `supabase/seed_legacy_events.sql`, generated deterministically by `fhc_api.legacy_import` from `events.json` (6 events + official-source rows).
- Local `admin_backend` login is set by `pnpm db:local-login` (docker exec). It is **not** a seed file, so it can never reach the cloud.
- API code:
  - `fhc_api.common.normalize` (`fold_turkish`, `slugify`, `normalize_url`) and `fhc_api.legacy_import`, with tests;
  - `apps/web/src/lib/database.types.ts` generated from `api`.
- Root scripts: `db:start`, `db:stop`, `db:reset`, `db:local-login`, `test:db`, `db:types`, `db:legacy-seed`.

**Checks run**
- `pnpm test:db`: 54 pgTAP tests pass (privileges, `api` surface, future-object defaults, visibility, constraints, forms, keep-alive).
- Mutation checks:
  - granting anon access to `app` → 3 tests fail;
  - a default EXECUTE grant in `api` → the future-object test fails;
  - after both are reverted, all pass.
- HTTP through PostgREST with the publishable key:
  - `events_public` 200 (6 rows);
  - `community_applications` 404; `app` / `public` profiles 406;
  - RPC valid 204, invalid 400 with the generic `invalid application`;
  - `keep_alive` 200.
- `admin_backend` logs in and does CRUD (inside a rolled-back transaction); it has no TRUNCATE.
- `pnpm lint`, `pnpm typecheck`, `pnpm test` (28 pytest), `pnpm build`: pass.
- The seed regenerates byte-identically.

**Review 1 (functional, self)**
- Found the local stack listening on all interfaces, plus a Docker firewall allow rule on the Public profile (SECURITY S8, owner decision pending).
- Found that the local stack answers without `apikey` (cloud check added to MVP criterion 6).

**Review 2 (independent subagent, read-only)**
- 5 must-fix findings, all fixed and verified:
  1. `IN SCHEMA` function revokes were no-ops, so new `api` functions were anon-executable (reproduced).
  2. Phone was stored for Telegram applicants.
  3. Telegram without a username was accepted.
  4. The privilege test compared lower-case `'public'` and missed grants made by other roles.
  5. The local password seed could reach the cloud via `--include-seed`.
- Also fixed:
  - `keep_alive` error leakage;
  - `public` default grants beyond CRUD;
  - non-string JSON values; empty and duplicate array items;
  - `published_at` required when published; sent publications need `external_id`;
  - non-empty normalized URL;
  - `admin_backend` default grants and timeout;
  - index changes: removed the redundant `event_sources(event_id)` index, added indexes for `source_id` and `duplicate_of`;
  - en-dash team sizes; `bool` SQL literals.
- Deferred (tracked, not blocking):
  - dedicated low-privilege owner for definer functions;
  - IANA timezone validation (API layer, M3);
  - `duplicate_of` cycles (V1.3);
  - `consent_version` allow-list (M5, with the notice text);
  - `normalize_url` edge cases (IPv6 brackets, scheme-aware default ports, percent-encoding case) — M3;
  - `first_sentence` abbreviations;
  - public list index on `start_date` (when M5 queries exist).

**M7 cloud checklist additions (from this milestone)**
- Set exposed schemas to `api` only in the dashboard (or `supabase config push`). `db push` does not carry `config.toml [api]`.
- Disable auth signup in the cloud project.
- Never use `db push --include-seed` except for the one-time legacy import.
- After the first push, compare `pg_default_acl` in the cloud with local.
- Verify that requests without `apikey` return 401.
- Verify that the session pooler accepts `admin_backend.<project-ref>`.

**S8 decision (owner, 2026-09-28):** accepted risk; no Docker/firewall change. Stop the local stack when not developing.

### M3 API core + M6 integrations (2026-10-05): done locally

**Built by three subagents in parallel worktrees, integrated and verified by the orchestrator.**
- **M3:**
  - Settings with pydantic-settings; psycopg pool (`admin_backend`); bearer token on every route except `/health`; `TrustedHostMiddleware`; consistent error mapping.
  - Events CRUD with the state machine and guards; slug generation with a race-safe retry; normalized URLs.
  - Sources and event sources; deterministic review signals with an SSRF-guarded fetcher (`httpx2`). The DB connection is released before the fetch.
  - Community and team applications; overview counts and heartbeats; `/system/db`.
  - Explicit OpenAPI operation ids; `/openapi.json` requires the token.
- **M6:**
  - `LLMProvider` + `OllamaProvider` (JSON-schema output, one repair retry, health states, localhost only) and the untrusted-content envelope.
  - Telegram client and check: the token never appears in errors or logs; post + edit required, delete optional, excess rights warned.
  - Model `qwen3.5:0.8b` pulled for the smoke test.
- **Wiring:**
  - clients created once and closed with an `ExitStack`;
  - misconfigured Telegram/Ollama settings do not stop the API (they surface in the checks);
  - `/llm/check` and `/telegram/check` sit behind the token.
- **D-20 pass 2:** `httpx2` supports timeouts, manual redirects, streaming with a size cap, `MockTransport`, and SNI with IP pinning. It is now a runtime dependency.

**Checks (re-run by the orchestrator):**
- `ruff check`, `ruff format --check`, `mypy` strict (76 files): pass.
- `pytest -W error`: 484 passed, 1 skipped (opt-in Ollama smoke test, which passed when run).
- Live HTTP on a separate port: auth, host check, `/overview`, `/system/db`, `/llm/check` with real Ollama, `/telegram/check` not configured.
- No test rows left in the DB.

**Review 1 (functional, orchestrator):** Telegram rights decision (least privilege); wiring tests added.

**Review 2 (independent subagent):**
- No critical or high findings.
- Fixed, 1 medium + 9 low:
  - startup resilience for bad integration config;
  - DB connection held during the review fetch;
  - slug race;
  - IPv6 embedded-IPv4 SSRF ranges;
  - least-privilege docs and excess-rights warning;
  - placeholder token rejected;
  - ValidationError handler that never logs personal data;
  - `trust_env=False`;
  - robust shutdown;
  - docs.
- Deferred, listed in LOCAL_ADMIN "Known limitations":
  - multi-address connect attempts;
  - per-chunk decompression cap (unused in V1);
  - 422 before auth on malformed unauthenticated bodies;
  - app INFO logging config.

### M5 Public web (2026-10-05): done locally

**Built by a subagent, reviewed independently, fixes verified by the orchestrator.**
- **Pages (Turkish-first):** `/`, `/hackathonlar` (Yaklaşan · Başvurular Açık · Son Günler · Geçmiş, Turkish-aware search, format/city filters, URL state, works without JS), `/hackathonlar/[slug]`, `/topluluk`, `/katki` (four intents), `/hakkinda`, 404 and error pages.
- **Data access:** server-only Supabase client (schema `api`, publishable key, no `NEXT_PUBLIC_`).
- **Caching:** Cache Components with a custom `events` cacheLife profile (revalidate 1 h, expire 2 h) and tags `events` and `event:<slug>`.
- **Phase rules:** `lib/phase.ts`, with timezone and DST tests.
- **Forms:** Server Actions → RPC, posted with POST (progressive enhancement); zod schemas mirror the DB rules. Bot filters: honeypot, client-measured elapsed time, consent versions. The KVKK notice is a marked TASLAK placeholder (Q9).
- **SEO:** metadata, JSON-LD Event, sitemap, robots, and a deterministic OG card (vendored Geist TTF, OFL). Turkish glyphs verified. Unknown cards return 404 `no-store` with tags.
- **Route handlers:** `/api/revalidate` (Bearer token, constant-time compare, tag schema) and `/api/cron/keep-alive` (`CRON_SECRET`, `no-store`); `vercel.json` sets a daily cron.
- **Security headers:** `X-Frame-Options`, `frame-ancestors`, `nosniff`, `Referrer-Policy`; `X-Powered-By` off.
- **Proxy:** malformed slugs get a real 404.

**Checks (re-run by the orchestrator on the branch merged with main):**
- lint, typecheck, build: pass. Tests: 75 passed.
- Client bundle: 0 secret matches.
- Live production server: security headers present; unknown OG card 404 `no-store`; malformed slug 404; form `method=POST`.

**Review 2 (independent subagent):**
- Fixed:
  - 1 high: a cached 404 for the OG card survived revalidation;
  - 1 medium: a no-JS submit leaked personal data into the GET query;
  - 10 low: ISR cache growth from unknown slugs, duplicate noindex, phase staleness up to 1 day, `SITE_URL` fallback, security headers, honeypot autofill, input border contrast 1.59 → 3.21, consistent Turkish "sen" address, security unit tests, `@types/node` ^24.
- Accepted: soft 404 (200 + noindex) for well-formed unknown slugs, plus a bounded 2 h shell cache entry (see PUBLIC_WEB).

**Not done:** Lighthouse (MVP 17) is to be measured at M7 on Vercel. There is no dark mode.

### M4 Local admin UI (2026-10-05): done locally

**Built by a subagent, reviewed independently, fixes re-verified by the orchestrator.**
- **dashboard-01 adapted, not redesigned.** Overview at `/` shows counters linked to filtered lists, keep-alive heartbeats that turn red after 48 h, and recent events. The chart and demo data are removed.
- **Pages:**
  - events list with filters and paging;
  - event create/edit (sends only changed fields; CRLF-safe comparison);
  - per-event Review page (event data | evidence: deterministic signals, duplicates, source tiers, event sources);
  - review queue;
  - community applications and contributions with status changes;
  - sources;
  - Settings (DB, Ollama with test output, Telegram including missing optional and excess rights, revalidation state).
- **Transitions:** the UI offers only the actions the API allows for the current status. Publish, unpublish, archive, reject and request-changes ask for confirmation. A 409 re-renders the page with the current state.
- **Security:**
  - API client is server-only; the token never reaches the browser (grep: 0).
  - Host allow-list proxy (`ADMIN_ALLOWED_HOSTS`, default `127.0.0.1,localhost`) on every route, including Server Actions. It checks Host, X-Forwarded-Host and Origin.
  - Pages show an "API not reachable" state when the API is down.
- Types are generated from the authenticated `/openapi.json` (`api:types`), with no `as unknown as` casts.
- Dependencies: added `server-only`, `openapi-typescript`, `vitest` 5. Removed recharts and dnd-kit.

**Checks (re-run by the orchestrator on the branch merged with main):**
- lint, typecheck, build: pass.
- Tests: admin 29, web 75, api 484 (+1 opt-in skipped); pgTAP 54.
- Live: a foreign Host or X-Forwarded-Host gets 400 on pages and `/api/health`; the correct host gets 200.

**Review 2 (independent subagent):** fixed 1 high, 1 medium and 9 low/nit.
- High: DNS rebinding let a foreign site read application data and run Server Actions through the admin; reproduced live.
- Medium: an untouched Save PATCHed multi-line fields (CRLF vs LF) and triggered revalidation.
- Low/nit: focus after dialogs and 422, pager bounds, duplicate Ollama check, type casts, Publish confirmation, explicit time zone, a wrong comment, regenerated API types.

**API gaps found (follow-ups, not blocking V1):**
- no endpoint to read whether revalidation is configured;
- no `GET /sources/{id}`;
- no health-only Ollama check (the check always runs a test generation);
- no delete for events or sources (test data had to be removed via SQL).

**M7 note:** the web build prerenders from the database, so Vercel builds need `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` set and the DB reachable at build time.

### M7 Cloud setup (2026-10-06): in progress

**Supabase**
- Free quota: the owner paused `akran-degerlendirme` to make room (the limit is 2 active free projects per user, across organizations).
- Project `firat-hackathon-community` (ref `idqnftpaekwokfehvfqz`), org "Bilal", region eu-central-1, Free. Created with the CLI; the DB password exists only in a local file for the owner's password manager.
- `db push`: both migrations applied, no seed.
- Config push was limited to `api.schemas = ["api"]`, `api.extra_search_path`, and `auth.enable_signup = false`. A diff confirmed nothing else changed; the full local config would have weakened cloud auth settings.
- `admin_backend` can log in (random password, stored only in the gitignored `services/api/.env.cloud`). **The session pooler accepts the custom role**, which was the open runbook risk.
- Legacy seed applied once: 6 published events, 6 event sources.
- `pg_default_acl` matches local for `app`/`api`; anon has no usage on `app` and can execute exactly 3 `api` functions.
- MVP #6 verified on the cloud: `events_public` 200 (6 rows); private table 404; `app` and `public` profiles 406; **no apikey → 401**; invalid keep-alive source → generic 400.

**Vercel**
- Project `firat-hackathon-community` (team bilalabic's projects, Hobby), Git-linked, Root Directory `apps/web`, framework nextjs, function region fra1 (same region as the DB).
- Env vars:
  - `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (production + preview);
  - `WEB_REVALIDATE_SECRET`, `CRON_SECRET` (production, sensitive, entered via stdin and never printed).
- `NEXT_PUBLIC_SITE_URL` falls back to `VERCEL_PROJECT_PRODUCTION_URL`.
- The CLI upload failed (the CLI does not use `.gitignore`), so deploys come from Git.
- `vercel link` appended `.vercel` and `.env*` to the root `.gitignore`. Reverted, because `.env*` would re-ignore `.env.example` files.
