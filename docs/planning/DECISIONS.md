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
- **V1.2:** `selectolax` 1.0.0 (MIT) and `trafilatura` 2.3.1 (Apache-2.0) added; versions and transitive licenses in CRAWLING_RESEARCH §1
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
- **Status:** Accepted (2026-10-06): option A; separate admin bot; no applicant details in Telegram. Plan: docs/planning/V1_1B_TELEGRAM_ADMIN.md

### D-22 KVKK notice and cross-border transfer basis
- **Options:**
  - A. Legal advice + standard contract before the forms go live.
  - B. Site live, forms closed until A is done.
  - C. Minimise the form data.
  - D. Keep everything live; explicit consent including a separate transfer-abroad statement.
- **Chosen:** D, by the owner, 2026-10-06 ("sitenin hiçbir özelliğinden kısmayalım … sorumluluk bende").
- **Notice:** `/aydinlatma-metni` (source `apps/web/src/lib/privacy.ts`). Controller Bilal Abiç, contact bilalabic78@gmail.com, retention 12 months, consent versions `2026-10-community-v2` / `2026-10-team-v2`.
- **Risk:**
  - Under KVKK m. 9 (in force since 2024-06-01), explicit consent covers occasional transfers. Storage with Supabase (Frankfurt) and processing through Vercel are regular transfers, so the basis may be insufficient.
  - Accepted by the owner (R-20).
  - The public notice is accurate about providers, locations and basis, and claims nothing more.
- **Revisit:** after legal advice, if the community grows, or when the Authority issues guidance or an adequacy decision.
- **Status:** Accepted (owner risk acceptance)

### D-23 Cloud LLM: OpenAI API (supersedes D-09 default)
- **Options:** keep local Ollama (D-09) · OpenAI Responses API with data sharing (complimentary daily tokens)
- **Chosen:** `LLM_PROVIDER=openai` with `OpenAIProvider` (raw REST over httpx2, no SDK, D-10/D-20). Model default `gpt-5.4-mini` (effort `none`) pending the benchmark; Ollama stays as the fallback provider (`LLM_PROVIDER=ollama`, still the code default until the owner switches)
- **Data sharing:** prompts and outputs may be used for training, and calls are a transfer to the US (D-22). Only public event pages go there; application data never does
- **Guards:** KVKK mask (`llm/pii.py`: e-mails, phones, valid TC Kimlik numbers) on every outbound string; architecture test keeps `fhc_api.community` from importing `fhc_api.llm`; `store: false`; dedicated project key with a **hard monthly spend limit**; in-process daily token budget (`OPENAI_DAILY_TOKEN_BUDGET`, follow-up: DB-backed counter); errors and logs never carry the key or prompt
- **Pass 1:** strict structured output with `maxLength`/`minimum` and `temperature: 0` at effort `none` verified live 2026-10-13 (OPENAI_API_RESEARCH §5)
- **Pass 2:** V1.2 benchmark 2026-10-13 (LLM_BENCHMARK, run 2): `gpt-5.4-mini` 92% accuracy, 100% date accuracy, 0 fabricated dates, 3.6 s and about 3.9k tokens per page → default model `gpt-5.4-mini`
- **Status:** Accepted (2026-10-13), owner decision; default model `gpt-5.4-mini` per the benchmark

### D-24 Discovery architecture: deterministic adapters first, web search as a gap-finder
- **Options:** A. LLM web search (OpenAI `web_search`) as the engine · B. curated source adapters + change detection as the engine, with watchlists, inbound links, web search and link expansion as supplements · C. generic JSON-LD harvesting (Common Crawl / Web Data Commons) · D. third-party search APIs (Brave, Exa, Tavily, SerpAPI)
- **Chosen:** B, in this priority:
  1. Source adapters + change detection (JSON endpoints, sitemaps with `lastmod`, JSON-LD, list-region hash, ID diff, conditional GET).
  2. Organizer/series watchlists (`app.event_series`).
  3. Admin-bot forwarded links and community suggestions (URL only).
  4. OpenAI `web_search` twice a week as a gap-finder: only citation URLs are used, never facts from the answer text; hosts that are not sources become source suggestions.
  5. One-hop link expansion from accepted events.
- **Scope:** in-person events in Türkiye and online events (global included). In-person events abroad are a hard reject.
- **Review load:** relevance threshold (score ≥ 40 → draft) and a daily cap of drafts (`DISCOVERY_MAX_DRAFTS_PER_DAY`, default 15, owner capacity 10–15/day). The rest wait in the queue.
- **Data:** `app.candidates` queue (claimed with `FOR UPDATE SKIP LOCKED`, no Redis), adapter columns on `app.sources` incl. `tos_status`, `app.event_series`, deterministic `relevance_score` + `relevance_reasons` per candidate.
- **LLM role:** triage and extraction (D-23 provider, `gpt-5.4-mini`), larger model only for retries and flagged dedup pairs. No LLM for relevance, verification or status.
- **Devpost:** integrated directly from V1.4a and enabled by default, although Devpost ToS §4 forbids automated access ("automated software, devices, scripts robots…", "scrape", "crawl", "spider"). **The owner accepts this risk (2026-10-13)** and chose not to request permission first. Mitigations:
  - only the public listing JSON and public event pages; no login, nothing behind authentication;
  - list fetch once a day; at most 1 request per 5–10 s; conditional GETs;
  - descriptive User-Agent with the site URL; robots.txt respected;
  - only event facts plus a link back to Devpost with attribution; no participant or user data;
  - kill switch `DEVPOST_ENABLED`, to turn the adapter off at once on a complaint or block;
  - no evasion: if Devpost blocks us, the adapter stops and is not worked around.
- **Reason:** most relevant events sit on fewer than 15 platforms and organizer pages with structured data. Adapters give complete lists at zero token cost with high precision; web search has medium recall and precision, varies between runs and is paid (`web_search` is not covered by the complimentary tokens).
- **Risks:** adapter rot on redesigns (0-item alarms, fixtures per adapter); ToS (R-21 Devpost, owner-accepted; other sources checked per source); paid search spend (R-23); queue flood (cap).
- **Pass 1:** robots, sitemaps and endpoints of 25 sources fetched on 2026-10-13 (DISCOVERY_RESEARCH §1). **Pass 2:** Coderspace's JSON API is `Disallow`ed, so its sitemap + JSON-LD are used instead; Luma, BTK Akademi, Techolay and DoraHacks are blocked or forbid automation and are never automated; Instagram, LinkedIn and Telegram channels only through human forwarding.
- **Revisit:** if gold-list recall from adapters stays below 70%, or web search finds more than adapters; on any complaint from a source.
- **Status:** Accepted (2026-10-13). Devpost risk: accepted by the owner (2026-10-13)

### D-25 Event types and type filters
- **Options:** A. hackathons only · B. free-text `categories` labels · C. a fixed `event_type` field
- **Chosen:** C. New enum `app.event_type` = `hackathon`, `ideathon`, `datathon` (incl. Kaggle-style competitions), `game_jam`, `competition` (Teknofest-style). Column `app.events.event_type` not null, default `hackathon` (the 6 legacy events and all current events are hackathons).
- **Where it appears:**
  - `api.events_public` (view recreated; pgTAP updated);
  - V1.2 extractor gets an `event_type` field (enum, with snippet); adapters set it from structured hints when they can;
  - admin: Events list filter and event form field;
  - public listing moves to `/etkinlikler` (owner, 2026-10-13): type filter beside format and city (URL parameter, Turkish slugs: `hackathon`, `ideathon`, `datathon`, `game-jam`, `yarisma`), labels in `lib/copy.ts`, a type badge in rows and on the detail page, JSON-LD unchanged (`Event`);
  - Telegram caption: a type label line (e.g. "Tür: Ideathon"). This changes the caption, so existing live posts show `changed` once and can be updated.
- **Reason:** the owner wants all five types; a fixed field gives reliable filters and is cheap to classify. `categories` stays for topics (Q12).
- **Route:** the public listing becomes `/etkinlikler` and `/etkinlikler/[slug]` with the title "Etkinlikler" (owner, 2026-10-13). `/hackathonlar` and `/hackathonlar/[slug]` answer with a permanent redirect (308) to the new path, so existing links, Telegram posts and search results keep working; sitemap, canonical URLs, the OG card URL and `WEB_BASE_URL` detail links switch to the new path.
- **Risks:** borderline events (a "hackathon" that is really a competition) → admin can change the type; a short SEO dip after the move.
- **Revisit:** add a type only when the gold list shows a recurring kind that fits none of the five.
- **Status:** Accepted (2026-10-13); built in V1.3

### D-26 Discovery scheduling: Windows Task Scheduler on the local machine
- **Options:** A. Windows Task Scheduler running a CLI · B. in-process APScheduler while the API runs · C. GitHub Actions / Vercel Cron in the cloud
- **Chosen:** A. Tasks run `uv run python -m fhc_api.discovery run --due` daily and the `web_search` sweep twice a week, with "Run task as soon as possible after a scheduled start is missed" (catch-up when the laptop was off) and "Do not start a new instance" if one is still running.
- **Reason:** keeps the local FastAPI as the single writer (D-05) and keeps the DB credentials and the OpenAI key on the laptop. Cloud runners would need both in the cloud and split the writer; they stay for keep-alive only (D-19).
- **Risks:** nothing runs while the laptop is off for days (catch-up runs on the next start; queue persists); a stuck run (per-run time limit, run row marked failed).
- **Revisit:** if the API moves to an always-on host (same trigger as D-21).
- **Status:** Accepted (2026-10-13); built in V1.5
