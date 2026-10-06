# Decision Log

Status values: **Proposed** (awaiting owner approval), **Accepted**, **Superseded**.

---

### D-01 Keep and evolve the repository (no rewrite-from-scratch in a new repo)
- **Options:** new repo · same repo monorepo
- **Chosen:** same repo, monorepo layout; the legacy site stays live until cutover
- **Reason:** keeps history, issues, the Pages URL and stars; the legacy code is small
- **Risks:** Pages workflow publishing new code (mitigated by S2 fix in M0)
- **Revisit:** if admin code must become private → split `apps/admin` + `services/api` into a private repo
- **Pass 1:** repo is small and clean. **Pass 2:** checked that no external consumer of `events.json` is known; the Pages artifact path must be narrowed first
- **Status:** Accepted (2026-09-28)

### D-02 Database: Supabase Postgres
- **Options:** keep JSON in git · Supabase · Neon + own API · SQLite on laptop
- **Chosen:** Supabase (schema `app` private, schema `api` exposed)
- **Reason:** shared by laptop and Vercel; RLS + Data API avoid building a public API; local Docker stack; SQL migrations
- **Risks:** free-tier pause (D-03); vendor-specific `api` exposure config
- **Revisit:** if we need server logic Supabase can't host, or costs change
- **Pass 1:** meets all sharing needs. **Pass 2:** legacy keys end 2026 → use new keys; default grants being revoked → dedicated `api` schema; views bypass RLS → deliberate definer view + pgTAP tests
- **Status:** Accepted (2026-09-28)

### D-03 Supabase plan: Free + keep-alive vs Pro
- **Options:** Free (7-day inactivity pause) + daily GitHub Actions ping of `api.events_public` · Pro ($25/month/project)
- **Chosen:** Free plan + redundant daily keep-alive (design in D-19). Owner requirement: the project must not pause
- **Risks:** a pause takes the public data offline; Free-plan terms may change; the docs describe "user requests" and do not explicitly allow or forbid synthetic pings
- **Pass 1:** official docs: "a few user requests to the database each day over the previous week is enough to keep the project from being paused"; 1-year restore window after pause. **Pass 2:** public traffic cannot be relied upon, and GitHub scheduled workflows alone are not enough (auto-disabled after 60 days without repo activity) → two independent schedulers + monitoring
- **Revisit:** if a pause warning email ever arrives, or Supabase changes the Free-plan terms → Pro
- **Status:** Accepted (2026-09-28)

### D-04 Admin framework: Next.js + shadcn `dashboard-01`
- **Chosen:** as requested; chart removed, table/cards repurposed
- **Pass 1:** block exists and matches required layout. **Pass 2:** considered Python-only admin (HTMX) to drop a runtime — rejected: owner explicitly wants shadcn dashboard; admin holds no credentials so the cost is only UI code
- **Status:** Accepted (2026-09-28)

### D-05 Backend: single FastAPI app as the only canonical writer
- **Options:** Next.js Server Actions → DB · FastAPI
- **Chosen:** FastAPI; admin Next.js calls it server-side with a bearer token
- **Reason:** Python needed from V1.2; one place for business rules
- **Risks:** two runtimes to set up; Python not yet installed on Windows (D-13)
- **Revisit:** if V1.2+ is dropped, collapse into Next.js
- **Pass 1/2:** see STACK_RESEARCH §6
- **Status:** Accepted (2026-09-28)

### D-06 DB access from FastAPI: psycopg 3 + plain SQL, Supabase CLI migrations only
- **Rejected:** SQLAlchemy ORM + Alembic (duplicate schema source)
- **Pass 2:** session pooler (IPv4, prepared statements OK) chosen over direct connection (IPv6-only without add-on)
- **Status:** Accepted (2026-09-28)

### D-07 Public framework: Next.js 16 on Vercel with Cache Components
- **Chosen:** tag-based on-demand revalidation (`revalidateTag(tag, {expire: 0})` in a Route Handler) + `cacheLife('hours')` fallback
- **Pass 1:** docs 16.3.6 confirm APIs. **Pass 2:** Hobby plan is non-commercial only (Q3); single-arg `revalidateTag` deprecated → two-arg form
- **Status:** Accepted (2026-09-28)

### D-08 Public data access: publishable key server-side, `api` view + RPC functions
- **Rejected:** secret key on Vercel (full-DB blast radius); anonymous table INSERT policies (exposes table, weaker validation)
- **Risk:** RPC callable directly with the publishable key → spam possible, no data exposure (R-07)
- **Status:** Accepted (2026-09-28)

### D-09 Local LLM runtime: Ollama; model chosen by benchmark in V1.2
- **Candidates:** `qwen3.5:4b`, `qwen3.5:9b`, `gemma4:e4b-it-qat`, `gemma4:e2b-it-qat` (+ `qwen3:8b` baseline)
- **Pass 1:** RTX 5070 (CC 12.0) supported; JSON-schema `format`. **Pass 2:** default `gemma4:e4b` (9.6 GB) does not fit 8 GB → qat tag; Qwen3.5 thinks by default → `think:false`; Turkish quality unverified → benchmark
- **Status:** Accepted (2026-09-28)

### D-10 LLM provider architecture: own `LLMProvider` Protocol, no LiteLLM/LangChain
- **Pass 2:** LiteLLM supply-chain compromise (2026-03-24) reinforces minimal dependencies; OpenAI-compatible class covers most cloud providers later
- **Status:** Accepted (2026-09-28)

### D-11 Version order: Telegram publishing moves to V1.1, discovery to V1.4
- **Reason:** value early, low risk; dedup must precede automated discovery
- **Status:** Accepted (2026-09-28)

### D-12 Telegram integration: direct Bot API over httpx2, no bot framework, no webhook
- **Pass 1:** Bot API 10.3 methods cover send/edit/delete/invite. **Pass 2:** local-only admin → outbound calls + optional long polling; caption limit 1024 shapes the template; 48 h delete ambiguity → test (T-1)
- **Status:** Accepted (2026-09-28)

### D-13 Python toolchain on Windows: install `uv` (user-level) natively
- **Options:** native Windows uv · WSL
- **Chosen:** native (CLAUDE.md: WSL only for tools unreliable on Windows; FastAPI/psycopg/Playwright work on Windows). Install `uv` and Ollama via `winget` (official packages); Python itself is managed by `uv python install`, not a global install
- **Status:** Accepted (2026-09-28): installation approved by owner

### D-14 Event card images: `opengraph-image` route on the public site (Satori), reused by Telegram
- **Rejected:** Playwright screenshots in FastAPI (heavy); generative images (factual risk)
- **Constraint:** card exists only for published events → web publish precedes Telegram post
- **Pass 2:** Satori supports flexbox only, ttf/otf/woff fonts, 500 KB bundle → simple template, Geist TTF, verify Turkish glyphs
- **Status:** Accepted (2026-09-28)

### D-15 Crawling stack (V1.2+): httpx2 + selectolax + trafilatura, Playwright only per-source; no Crawl4AI; no SQLite
- **Status:** Accepted (2026-09-28)

### D-16 Provenance: event-level `event_sources` in V1; field-level evidence in V1.2
- **Reason:** manual entries have no snippets to store; extraction does
- **Status:** Accepted (2026-09-28)

### D-17 Publication model: `publications` rows with content hash of a publishable projection
- **Rejected:** `published=true` flag; revisions as the change detector
- **Status:** Accepted (2026-09-28)

### D-18 Public UI language
- **Conflict:** instructions require English UI; audience and current content are Turkish
- **Options:** English only · Turkish only · bilingual (next-intl, `/en`, `/tr`)
- **Chosen:** code, docs, DB, API and **admin** in English; **public UI Turkish-first** (`lang="tr"`, Turkish copy, Turkish date formatting); English public UI may be added in V2. Event content stays in its original language
- **Implementation note:** keep all public UI strings in one `apps/web/lib/copy.ts` (not scattered), so adding English later does not need a rewrite. No i18n framework in V1
- **Status:** Accepted (2026-09-28)

### D-20 HTTP client: `httpx2` everywhere in the API
- **Options:** `httpx` (0.28.x) · `httpx2`
- **Chosen:** `httpx2` for the test client and for runtime clients (Telegram, fetcher, Ollama, web revalidation)
- **Reason:** Starlette 1.7 deprecates `httpx` in `TestClient` and recommends `httpx2` (published by the pydantic org, 2.13.1). One HTTP client in the codebase
- **Pass 1:** swapped the dev dependency; pytest passes with `-W error`. Transitive `truststore` (system certificate store) is installed. `httpx2-jsfetch` applies only to `emscripten` and is not installed. **Pass 2 (M3):** confirm the runtime API parity we rely on (timeouts, redirect limits, streaming with size cap, transport mocking in tests) at first runtime use
- **Revisit:** if a runtime feature we need is missing or unstable in `httpx2`
- **Status:** Accepted (2026-09-28, owner instruction)

### D-19 Supabase keep-alive design
- **Options:** single GitHub Actions cron · single Vercel Cron · both + heartbeat monitoring · paid plan
- **Chosen:** both, independent, with a visible heartbeat:
  1. **Primary: Vercel Cron** (`apps/web/vercel.json`, daily, e.g. `0 3 * * *` UTC; Hobby = once/day, ±59 min) → `GET /api/cron/keep-alive`, checked with `Authorization: Bearer ${CRON_SECRET}` (Vercel sends it automatically) → `api.keep_alive('vercel_cron')`
  2. **Secondary: GitHub Actions** `schedule` (daily, e.g. `0 15 * * *` UTC, 12 h offset) → `curl` the same RPC with the publishable key (Actions secret) and source `'github_actions'`; also runs `workflow_dispatch`
  3. **Monitoring:** `api.keep_alive` records `app.heartbeats(source, last_seen_at)` and runs a real read. The admin Overview shows each source's last heartbeat and turns red after 48 h. Supabase itself emails a warning about 1 week before a pause
- **Pass 1:** Vercel Cron and GitHub `schedule` both verified in official docs. **Pass 2:** GitHub disables scheduled workflows in public repos after 60 days without repo activity, and scheduled runs can be delayed or dropped under load. Vercel Cron is best-effort with no retries, so each one alone is insufficient. Two schedulers 12 h apart + monitoring + Supabase's warning email give three independent chances to notice. The endpoint is idempotent (it sets a timestamp, never increments)
- **Status:** Accepted (2026-09-28)

### D-21 Admin decisions via Telegram
- **Options:** A local long-polling bot inside the admin API · B cloud webhook (Vercel / Edge Function) with DB write access · C Telegram Mini App hosting the admin UI
- **Proposed:** A for V1.1b. The bot sends review/approval/application notifications with inline buttons and executes them through the existing service layer.
  - Guards: admin allowlist by numeric user id; stale-press protection (state token in `callback_data`, max press age); two-step confirm for Publish/Reject; persisted update offset; audit table `app.admin_actions`.
  - Personal data in Telegram: counts and first names only.
- **Reason:** keeps one writer (D-05), the publishable-key-only public site (D-08) and the token on the laptop. No new public endpoint.
- **Trade-off:** decisions run only while the laptop/API is on. Telegram keeps undelivered updates for up to 24 h; stale presses are refused.
- **Revisit:** if approvals are routinely needed while the laptop is off. Then move the API to an always-on host rather than splitting logic into a webhook.
- **Pass 1:** Bot API 10.3: `callback_data` 1–64 bytes, getUpdates long polling, 24 h retention, webhook `secret_token`; webhook and getUpdates are mutually exclusive; Mini App initData HMAC. **Pass 2:** B and C each widen the attack surface and duplicate or relocate business rules; A reuses M3/M6 code.
- **Status:** Proposed (owner decision pending)
