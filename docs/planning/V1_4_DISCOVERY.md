# V1.4: Discovery

Status: **plan**, 2026-10-13. Inputs: [DISCOVERY_RESEARCH](../research/DISCOVERY_RESEARCH.md),
[OPENAI_API_RESEARCH](../research/OPENAI_API_RESEARCH.md), [CRAWLING_RESEARCH](../research/CRAWLING_RESEARCH.md).
Decisions: D-23 (OpenAI provider), D-24 (discovery architecture), D-25 (event types and filters),
D-26 (scheduling), all **Accepted 2026-10-13** (text in [DECISIONS](DECISIONS.md)).
Depends on V1.2 (extraction) and V1.3 (dedup + event types). Scheduling is V1.5.

## Goals

1. Find every event a Fırat student can join, without the admin searching by hand:
   **in-person events in Türkiye** plus **online events (global included)**. In-person events abroad
   are out of scope (hard reject, also for hybrid events unless online participation is allowed).
2. Event types: **hackathon, ideathon, datathon (incl. Kaggle-style), game jam, competition
   (Teknofest-style)**. All are in scope; the type is a field on the event (D-25).
3. Deterministic first: structured data (JSON, sitemaps, JSON-LD) is the engine; LLM web search is
   only a gap-finder.
4. Fit the review capacity: **10–15 drafts/day** at most, ranked by an explainable relevance score.
5. Keep the rules: AI proposes, code decides, a human approves (AI_ARCHITECTURE). The local FastAPI
   stays the single writer (D-05). No event exists without a fetched page and per-field evidence.

Non-goals: automatic publishing, automatic merges, crawling behind logins or bot walls, social
media scraping, cloud runners.

## Pipeline

```text
 strategies (by priority)                      shared stages
 1 source adapters + change detection ─┐
 2 series watchlist                    ├─► candidate ─► URL dedup ─► triage ─► fetch ─► extract
 3 admin-bot forwards + community form ┤    (queue)     (+ V1.3       (LLM,    (Safe-   (V1.2,
 4 web_search sweep (2×/week, paid)    ┤                 matcher)     no tools) Fetcher) evidence)
 5 one-hop link expansion              ┘
        ─► scope + relevance score (rules) ─► daily cap ─► draft event + evidence ─► admin review
```

| Stage | What it does | Notes |
|---|---|---|
| Discover | Adapter lists items (title, URL, dates, location hints). Change detection: conditional GET (`ETag`/`Last-Modified`), sitemap `lastmod`, list-region hash, ID diff | 0 tokens. A re-run on an unchanged source creates 0 candidates |
| Candidate | Upsert into `app.candidates` by `url_normalized`; a re-sighting only bumps `last_seen_at`/`seen_count` | Workers claim with `FOR UPDATE SKIP LOCKED` |
| Dedup | Exact URL against candidates, `events.official_url_normalized`, `event_sources.url_normalized`, **before any fetch**; then the V1.3 candidate-aware matcher (title + dates + organizer on hints) | Uncertain → `duplicate_candidates`; never an automatic merge |
| Triage | "In scope? Which type? Still open?" on title + snippet + hints | Skipped when the adapter is type-specific and hints are complete |
| Fetch + extract | SafeFetcher, robots, per-host rate limit; V1.2 extractor incl. `event_type` | Evidence check unchanged |
| Score | Deterministic rules → `relevance_score` + `relevance_reasons` | No LLM |
| Cap | Score ≥ 40 → draft, at most `DISCOVERY_MAX_DRAFTS_PER_DAY` (default 15), ordered by deadline urgency then score; the rest stay `queued` for the next day | 15–39 → "Low relevance" tab; < 15 hidden but kept for recall audits |

### Relevance rules (summary; full list in DISCOVERY_RESEARCH §3.4)

Hard rejects: deadline or end in the past; in person outside Türkiye; eligibility excludes Türkiye
or non-members (Devpost `invite_only`, "US residents only"); type not one of the five.
Points: online and open worldwide +25; in person in Elazığ / East Anatolia +30, elsewhere in Türkiye
+15 (+5 travel or accommodation support); students or beginners welcome +10; Turkish or English +5,
otherwise −30; deadline ≥ 7 days away +10, < 3 days −10; Tier 1/2 source +10; only Tier 4 →
`needs_verification`. Weights live in code with tests; each applied rule is one
`relevance_reasons` item `{rule, points, evidence_field}` and is shown on the review page.

## Data (migrations in V1.4a unless noted)

- **`app.event_type` enum + `events.event_type`**: V1.3 (D-25), see ROADMAP.
- **`app.sources` + adapter columns**: `adapter text` (registry key: `devpost_json`, `sitemap`,
  `jsonld_list`, `list_page`, `announcement_ids`, `kaggle_api`, `web_search`), `config jsonb`
  (URL patterns, filters), `check_interval interval`, `next_check_at`, `last_checked_at`, `etag`,
  `last_modified`, `list_hash`, `robots_checked_at`, `crawl_delay_s`, `consecutive_failures`,
  `last_item_count`, `tos_status text` (`ok` · `unverified` · `owner_accepted_risk` · `blocked`),
  `status_reason text`. `enabled` already exists.
- **`app.candidates`**: `id, url, url_normalized unique, source_id, run_id, discovered_via`
  (`adapter` · `sitemap` · `watchlist` · `bot_forward` · `community` · `web_search` · `link`),
  `hints jsonb` (with provenance), `status` (`new` · `triaged_out` · `queued` · `fetched` ·
  `drafted` · `duplicate` · `rejected` · `error`), `triage jsonb`, `event_type_hint`,
  `relevance_score smallint`, `relevance_reasons jsonb`, `event_id` FK, `content_hash`,
  `first_seen_at, last_seen_at, seen_count, next_fetch_at, attempts, last_error`.
  Retention: `triaged_out` / `rejected` rows deleted after 180 days.
- **`app.runs`**: `kind` check extended with `discovery`, `web_search`; `stats` holds item,
  candidate and draft counts, tokens per model, `web_search` calls.
- **`app.event_series`** (V1.4b): `id, name, organizer, event_type, source_id, typical_month,
  last_event_id, watch_urls text[], expected_from, expected_to, status`.
- **`app.source_suggestions`** (V1.4c): hosts found by web_search or link expansion that are not
  a source yet (`host unique, sample_url, seen_count, status`). The admin turns them into sources.
- **`api.submit_event_suggestion(url, note)`** (V1.4b): anonymous RPC like the application RPCs;
  URL required, note ≤ 300 chars, no name or contact field, so no personal data is collected.
- Same RLS/grant pattern as the other `app` tables (admin_backend only); pgTAP for each.

## Sources

Status: **E** enabled at launch of the milestone · **D** disabled by config · **B** blocked (never
automated) · **M** manual only.

| Source | Method | Status | Reason |
|---|---|---|---|
| Coderspace | `sitemap-events.xml` `lastmod` → detail JSON-LD | E (V1.4a) | robots allows `/etkinlikler/`; **its JSON API is `Disallow`ed, so not used** |
| Techcareer | `sitemap-events.xml` (`/hackathon/` prefix) | E (V1.4a) | robots allows |
| dev.events TR | `/hackathons/AS/TR` JSON-LD + `rss.xml` | E (V1.4a) | robots allows; Tier 4 aggregator → needs Tier 1/2 page |
| Youthall | sitemap (lastmod useless) + list-region hash | E (V1.4a) | robots allows |
| lablab.ai | sitemap index (`ai-hackathons`) | E (V1.4a) | robots allows public pages |
| Fırat Üniversitesi announcements | ID diff ("new since max ID") | E (V1.4a) | empty `Disallow` |
| **Devpost** | public list JSON (`/api/hackathons`, open + upcoming), once a day; public event pages | E (V1.4a), kill switch `DEVPOST_ENABLED` | ToS §4 forbids automated access; **owner accepted the risk 2026-10-13** (D-24, R-21). Mitigations below |
| Teknofest | seasonal competitions list page (hash) | E (V1.4b) | robots allows; type `competition` |
| Kaggle | official API (owner's API token) | D until token is set (V1.4b) | official interface; datathons are in scope |
| Patika.dev, Unstop (online + eligibility "All" only), MLH (online events only) | sitemap / public JSON / HTML | E (V1.4b) | robots allow (Unstop explicitly `Allow: /api/public/*`); ToS unverified, review before enabling |
| Taikai, TÜBİTAK duyurular | sitemap / HTML | D (later) | low relevance; enable if the gold list shows misses |
| Luma | — | B | ToS: "publicly supported interfaces" only |
| Eventbrite, Meetup | — | D | robots disallow feeds/APIs; 0 hackathons in samples |
| BTK Akademi, Techolay `/hackathon/` | — | B | WAF / HTTP 403 to our UA; never bypass |
| DoraHacks | — | B / M | bot wall; admin imports single URLs by hand |
| Devfolio, Hackathon.com | — | D | India-focused / SPA without links; postponed |
| Instagram, LinkedIn, Telegram channels, WhatsApp | forward to the admin bot | M | robots/ToS forbid scraping; humans forward links (V1.4b) |
| OpenAI `web_search` | Responses API tool, citation URLs only | E (V1.4c), 2×/week | paid (not in free tokens); gap-finder only |

### Devpost mitigations (owner-accepted risk)

- Only the public listing JSON and public event pages; no login, nothing behind authentication.
- List fetch once a day; at most 1 request per 5–10 s (per-host bucket, default 8 s);
  conditional GETs.
- Descriptive User-Agent with the site URL (the existing `common/http.py` UA).
- Respect robots.txt (checked and cached 24 h; fail closed on 5xx).
- Store only event facts plus a link back to Devpost with attribution ("Kaynak: Devpost");
  no participant or user data (no team members, no profiles, no submissions).
- Kill switch `DEVPOST_ENABLED` (default `true`): turn off at once on a complaint or block.
- No evasion: on 403/429-without-`Retry-After`/captcha the adapter sets `tos_status = blocked`,
  disables itself and raises an Overview alarm. No IP or UA rotation, no headless browser.

## LLM role per stage and token budget

Provider: OpenAI Responses API (D-23), default model **`gpt-5.4-mini`** (pending the V1.2 OpenAI
benchmark), effort `none`, `store: false`, strict JSON schema, `PIIGuard` before every send.
Ollama stays as fallback (`LLM_PROVIDER=ollama`, or automatically when the daily budget is hit).

| Stage | LLM | Model | Tokens/day (est.) | Pool |
|---|---|---|---|---|
| Discover (adapters, watchlist) | No | — | 0 | — |
| Query templates (TR + EN × type × month) | No; mini proposes new terms monthly | mini | ~0 | small |
| web_search sweep | Yes, only the `web_search` tool | mini | ~3 calls + ~30k content tokens (avg) | **paid** |
| Triage | Yes, enum schema, ≤ 1k in | mini | 40 × 1k = 40k | small (free) |
| Extraction | Yes (V1.2 extractor) | mini | 15 × 12k = 180k | small (free) |
| Retry on `llm_error` / conflict | Yes | `gpt-5.4` | 3 × 12k = 36k | large (free) |
| Dedup (flagged pairs only) | Yes | `gpt-5.4` | 5 × 2k = 10k | large (free) |
| Relevance, verification | **No** (rules + human) | — | 0 | — |

Total ≈ 220k/day small pool (cap 2.5M) and ≈ 50k/day large pool (cap 250k), if the
complimentary-token caps apply to the org (open item). Guards: `OPENAI_DAILY_TOKEN_BUDGET`
counted in our code from `usage`; `DISCOVERY_MAX_EXTRACTIONS_PER_DAY` (default 30) for backfills;
a dedicated OpenAI project with a hard monthly spend limit ($5) for the paid `web_search` calls.

## KVKK and ToS guardrails

- **Never** send application data (community/team rows, names, contacts, Telegram ids, notes) to
  any LLM; architecture test: the applications domain cannot import `llm/`.
- Public pages go through `PIIGuard` (emails, phones, TC Kimlik numbers redacted) before OpenAI.
  Data sharing is enabled only on the project that carries public page text.
- Community suggestions carry a URL and an optional note; the note is never sent to an LLM.
- Admin-bot forwards: only the URL(s) in the forwarded message become a candidate; the sender
  name and the forwarded text are not stored.
- Per source: robots.txt, rate limit, `tos_status`; never fetch through logins, bot walls or
  `Disallow`ed paths. Social and Telegram content arrives only by human forwarding.
- Prompt injection: page text and search results are untrusted (envelope, no tools in
  triage/extraction, schema output, only citation URLs from search, every URL re-fetched).
- Stored per event: facts + source links (`event_sources`); no copying of descriptions beyond
  the evidence snippets.

## Metrics (metrics page in V1.4c; counters from V1.4a)

- **Recall** per strategy = gold ∩ found / gold (adapters, watchlist, inbound, web_search, links).
- **Precision** = drafts accepted / drafts created; 10% sample audit of `triaged_out`.
- **Freshness** = median(first_seen_at − announcement date, when known).
- **Load** = drafts/day vs the cap; **cost** = tokens/day per model, `web_search` calls and $.
- **Health** = sources with 0 items, failures, `blocked`.

**Gold list (starts now, no code):** the owner and admins record every in-scope event they see by
any means for 4 weeks (target ≥ 30) in `services/api/bench/data/discovery_gold.csv`
(gitignored; copy the template `services/api/bench/discovery_gold.template.csv`): `title, official_url, event_type, format, city, deadline, seen_on, seen_via, notes`. `event_type` is one of hackathon, ideathon, datathon, game_jam, competition; `format` online, in_person or hybrid; dates are `YYYY-MM-DD`.
It is imported into the metrics in V1.4a.

## Milestones

| # | Content | Done when |
|---|---|---|
| **V1.4a** | `candidates` queue + `sources` adapter columns + `runs` kinds; adapter framework (robots, per-host bucket, conditional GET, list hash, back-off, 0-item alarm); adapters Coderspace, Techcareer, dev.events, Youthall, lablab, Fırat announcements, **Devpost** (with the mitigations and `DEVPOST_ENABLED`); triage; scope + relevance score + reasons on the review page; daily draft cap; "Run now" per source; gold list import | 7 adapters with fixture tests; a re-run on unchanged sources creates 0 candidates; drafts/day ≤ cap; ≥ 70% gold recall from adapters alone; Devpost kill switch and block handling tested |
| **V1.4b** | `event_series` watchlist (create from an accepted event, predicted window, check from 8 weeks before); admin-bot forward → candidate; `api.submit_event_suggestion` + form on `/katki`; Teknofest, Kaggle, Patika, Unstop, MLH adapters | Watchlist predicts ≥ 1 real new edition; a forwarded link becomes a candidate in < 1 min; a community suggestion becomes a candidate and stores no personal data (pgTAP) |
| **V1.4c** | `web_search` sweep (TR + EN templates, `user_location: TR`, citation URLs only, hard spend limit); `source_suggestions`; one-hop link expansion from accepted events (same or allowlisted hosts); metrics page | Combined recall ≥ 90% of gold; precision ≥ 60%; tokens and spend within budget for 7 days; web_search recall share reported |

## Open items

- OpenAI org usage tier and whether the complimentary-token program covers `gpt-5.4-mini` /
  `gpt-5.4` on Responses for our org (Q17).
- Which channels admins follow for forwarding (Q19). The owner maintains the gold list (Q18).
- ToS review (unverified in research) for Techcareer, Youthall, dev.events and lablab before
  V1.4a enables them, and for Patika, Unstop, MLH before V1.4b. A clause against automated access
  sets the source to D and goes to the owner (as Devpost did).
- Kaggle API token (owner) and Kaggle API terms check.
