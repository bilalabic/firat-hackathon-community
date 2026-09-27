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
- Starlette 1.7 emits a deprecation warning for `httpx` in `TestClient` and recommends `httpx2`. Adding `httpx2` needs owner approval (the tool permission was denied), so `httpx` is kept for now.
- Terminals opened before the `uv` install need a restart to find `uv`.
