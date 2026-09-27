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

**Open (owner):** SECURITY S8. Bind Docker to `127.0.0.1` or disable the Docker firewall rule. Until then, run `pnpm db:stop` when not developing.
