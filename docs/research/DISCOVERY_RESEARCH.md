# Discovery Research (V1.4 input)

Checked 2026-10-13 (all URLs accessed that day). Builds on CRAWLING_RESEARCH.md (retrieval order,
tiers, fetcher security) and D-11, D-15, D-16, D-22. **Research only; nothing here is built.**
"Verified" = fetched by us on 2026-10-13 with UA `FHCResearch/0.1 (+repo URL)`. "Unverified" = from
docs or third parties, or not tested.

**Question:** is there a primary discovery method better than LLM web search? **Yes.** Most of the
relevant events sit on fewer than 15 platforms and organizer pages. Their structured data (JSON
endpoints, sitemaps with `lastmod`, schema.org `Event` JSON-LD) can be read deterministically, at
zero token cost and with near-perfect precision. LLM web search is the **gap-finder**, not the engine.

## 1. Source inventory

Relevance: **H** = regularly lists events Fırat students can join (Turkish, or online and open
worldwide). **M** = some. **L** = rare.

### 1.1 Turkish sources

| Source | Structured data (verified) | robots.txt / ToS | Update rate | Rel. |
|---|---|---|---|---|
| Coderspace `coderspace.io/etkinlikler` | `sitemap-events.xml`: 366 URLs with `lastmod`, 39 hackathon slugs. HTTP `Last-Modified` header. Detail pages carry `Event` JSON-LD (+`VirtualLocation`) | Allows `/etkinlikler/`. **Disallows `/events/api/` and `/api/v1.0/`**, so the JSON API is off-limits. No anti-automation clause found in `/kullanicisozlesmesi` | Weekly | **H** |
| Techcareer `techcareer.net/hackathon` | `sitemap-events.xml`: 1009 URLs, 99 under `/hackathon/`, `lastmod` present | Allows everything except click-tracking paths. ToS unverified | Weekly | **H** |
| Youthall `youthall.com/tr/etkinlikler` | `sitemap.tr-events.xml`: 1148 URLs, about 8 hackathons. `lastmod` is regenerated daily for nearly all URLs, so it is useless as a change signal. Detail pages have no `Event` JSON-LD | `Allow: /`. `GPTBot` disallowed; `OAI-SearchBot` allowed. ToS unverified | Weekly | M |
| Teknofest `teknofest.org/tr/competitions` | `tr/sitemap.xml` (145 URLs, no `lastmod`). No `Event` JSON-LD. Large page (1.2 MB) | Allows competitions | Yearly cycle (applications roughly Nov–Feb, unverified) | **H** (seasonal) |
| Patika.dev | `sitemap.xml`; `Allow: /` | — | Irregular | M |
| Fırat Üniversitesi `firat.edu.tr/tr/page/announcement/<slug>-<id>` | No RSS found. IDs increase (e.g. 7622), so "new since max ID" is a cheap change test. `Disallow:` empty | — | Daily, mostly unrelated | M (local) |
| TÜBİTAK `tubitak.gov.tr/tr/duyuru` | HTML list, no RSS found | Drupal default robots (assets only) | Weekly; mostly grants | L–M |
| BTK Akademi | Our requests got a WAF page ("İstek Reddedildi") or timed out | Blocked, so do not bypass | — | Postpone |
| Techolay `/hackathon/` | HTTP 403 to our UA. The RSS `/feed/` works but is general tech news | — | — | L |
| Kariyer.net | Sitemap; robots restrict `/filtre` and profile pages. No events section found | — | — | L |
| Teknoparks, university clubs, GDG/IEEE chapters | Varies (often WordPress `/feed/`, Instagram-only for clubs) | Varies | Irregular | M, curated per organizer |
| Luma `luma.com/istanbul` | City page: 16 `Event` JSON-LD items, 2 mentioning "hackathon" | Only Googlebot rules. ToS: "must not access the Service by any means other than our publicly supported interfaces" | Daily | L (precision too low) |
| Eventbrite `/d/turkey/hackathon/` | 19 `Event` JSON-LD items, **0 hackathons** in the sample | Disallows `/rss/`, query variants. Event search API deprecated (CRAWLING_RESEARCH C-2) | — | L |
| Meetup `/find/?keywords=hackathon` | 12 `Event` items, 0 hackathons | Disallows feeds and `/meetup_api/`. ToS not read | — | L |
| Instagram / LinkedIn | — | Instagram: `User-agent: * Disallow: /` and Meta's automated-collection terms. LinkedIn: `Disallow: /` for `*`, crawling only with written permission | — | **Excluded** (manual only) |
| Telegram public channels | `t.me/s/<channel>` previews render publicly (verified) | Telegram ToS: "prohibits data scraping" (Content Licensing and AI Scraping Terms) | — | Use **forward-to-bot** instead (§2e) |

### 1.2 Global sources

| Source | Structured data (verified) | robots.txt / ToS | Rel. |
|---|---|---|---|
| Devpost | `GET devpost.com/api/hackathons?status[]=open&status[]=upcoming` returns JSON: `meta.total_count` 163, 9 per page, `page=`, `challenge_type[]=online` (63), `order_by=recently-added`, `search=`, weak `ETag`. Fields: title, url, `submission_period_dates`, `displayed_location`, themes, `prize_amount`, `invite_only`, `eligibility_requirement_invite_only_description`. **Undocumented** | robots `Disallow:` empty for `*`. **ToS §4 forbids** using "automated software, devices, scripts robots… to access", "scrape", "crawl" or "spider" the Site | **H** (online) |
| dev.events `/hackathons/AS/TR` | 33 `EducationEvent` JSON-LD items (online events reachable from TR, many mirrored from Devpost). Global `rss.xml` (verified) | `Allow: /`; only Meta bots blocked. ToS unverified | **H** (as Tier 4 aggregator) |
| MLH `mlh.com/seasons/2027/events` (`mlh.io` redirects) | Server HTML, 83 event slugs, outbound links to official sites. No JSON-LD | Allows `/`; disallows `/graphql`, `/v4/` | L–M (mostly US/EU in person; Global Hack Week is online) |
| Unstop | `GET /api/public/opportunity/search-result?opportunity=hackathons&oppstatus=open` returns JSON (264 open, with `region` and eligibility `filters`) | robots explicitly `Allow: /api/public/*`. ToS unverified | L (India-focused; keep `region=online` + eligibility "All" only) |
| Devfolio | Next.js `__NEXT_DATA__`; no public API found (guessed endpoint 404) | `Disallow:` empty | L (India) |
| DoraHacks | API and `/robots.txt` return a "Human Verification" page (HTTP 405) | Bot wall, so **do not bypass** | M (Web3, online), manual only |
| Hackathon.com | SPA; `/country/turkey` has no event links in HTML; sitemap 404 | `Disallow:` empty | Unverified; postpone |
| Kaggle | Official API (`/api/v1/competitions/list` → 401 without a token; needs the user's API key) | Official API, so preferred over HTML | L (competitions, not hackathons) |
| Taikai | `sitemap.xml` (3485 URLs incl. `/hackathons`). `Content-Signal: search=yes, ai-input=yes, ai-train=no` | Allows except `/auth` | L–M |
| lablab.ai | `sitemap.xml` index → `server-sitemap/ai-hackathons/*` | Allows public pages | M (online AI hackathons) |
| ETHGlobal | No robots file (CRAWLING_RESEARCH) | — | L, manual watch |

**Top 8 for V1.4** (by relevance × structure × legal clarity): Coderspace (sitemap + JSON-LD),
Techcareer (sitemap), Devpost (JSON, *pending permission*, see §5), dev.events TR (JSON-LD/RSS),
Teknofest (seasonal list page), Youthall (sitemap, content hash), lablab.ai (sitemap),
Fırat/area university announcement pages (ID diff). Patika, Unstop (filtered) and MLH come next.

## 2. Discovery strategies compared (baseline: LLM web search)

| Strategy | Recall | Precision | Freshness | Cost/day | Maintenance |
|---|---|---|---|---|---|
| **(b) LLM web search** (OpenAI `web_search`) — *baseline* | Medium: finds what search engines rank; weak for new small Turkish pages, and the result set varies between runs | Medium: answer text can merge or invent events; citations are reliable URLs only | Index lag of days; no date filter, only prompts | $10 / 1k calls + search content tokens at model rates ([pricing](https://developers.openai.com/api/docs/pricing)) | Low (prompts) |
| **(a) Curated adapters** (API/JSON, sitemap `lastmod`, list page diff → detail JSON-LD) | **High** for covered platforms (complete lists), zero outside them | **High**: structured fields, only hackathon slugs/categories | **Hours** (poll daily, conditional GET) | 0 tokens to list; extraction only for new URLs | Medium: one small adapter per source; breaks on redesigns (detect by "0 items" alarms) |
| (a′) Generic JSON-LD harvesting at scale (Common Crawl / Web Data Commons) | High in theory | Low (any `Event`) | **Weeks to months**: latest CC index `CC-MAIN-2026-39` ends 2026-09-17 ([collinfo](https://index.commoncrawl.org/collinfo.json)) | Free, but heavy | High |
| (c) Link-graph expansion (one hop from known events/organizers: "past editions", partner, sponsor, "other events" links) | Medium (finds organizers, series) | Low–medium, so triage is needed | As fresh as the seed | Few fetches | Low if limited to 1 hop + same/allowlisted hosts |
| (d) Organizer/series watchlist ("X Hackathon 2025" → expect 2026 around the same month) | High for recurring events (Teknofest, company series on Coderspace/Techcareer, IEEE, university clubs) | **High** | Early: check from about 8 weeks before the predicted window | ~0 | Low: a row per series |
| (e) Inbound signals: Telegram forward-to-bot, community "Etkinlik öner" | Covers Instagram/LinkedIn/WhatsApp-only events nobody can crawl | Medium (humans) | Immediate | 0 | Low; reuses the V1.1b admin bot |
| Search APIs with date filters (Brave, Exa, Tavily, SerpAPI) | Similar to (b) | Raw results (no invented answer), but noisy | Brave/Exa/Tavily offer freshness/date filters (parameter names unverified, see docs) | Brave $5 free credit/month ≈ 1k requests; Exa $10/month free; Tavily 1000 credits/month; SerpAPI 250/month | Low; adds a vendor + ToS (Brave requires a storage-rights plan to store results) |

Dead options: Bing Search API retired 2025-08-11
([Microsoft](https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement)).
Google Custom Search JSON API is closed to new customers and ends 2027-01-01 (third-party reports,
e.g. [Brave](https://brave.com/learn/google-api-shutdown/)).

Observation from the probe: dev.events' TR page and Devpost's open list overlapped strongly
(Amazon, Nebius, PayPal, Qloo, MLAI all appeared in both). Aggregators therefore give recall
**without** hitting Devpost directly. The Tier 1/2 page is still needed for verification.

### Ranked recommendation

1. **Primary engine: curated source adapters + change monitoring** (a). Deterministic, cheap,
   reviewable, legal per source. Target: ≥ 80% of the gold list (§3.6) found here.
2. **Series watchlist** (d): turns last year's events into this year's early alerts.
3. **Inbound signals** (e): forward a post/link to the admin bot → candidate. This is the only lawful
   route for Instagram/LinkedIn/Telegram-channel announcements.
4. **OpenAI web_search sweep** (b), 2×/week, as a gap-finder. Every search-found URL whose host is
   not yet a source is a **source suggestion** for the admin, so the adapter set grows where
   recall is missing.
5. **Link expansion** (c), one hop, only from accepted events, results through triage.
6. Not now: Common Crawl/WDC (too stale; maybe a one-time seed of organizer domains); extra search
   APIs (only if web_search proves weak on Turkish queries; Brave first).

**LLM role per stage**

| Stage | LLM? | Model class |
|---|---|---|
| Query generation | Template-first (TR + EN × topic × month window, e.g. "hackathon başvuru Kasım 2026", "online hackathon students worldwide November 2026"); mini only to propose new terms from accepted events | mini |
| Search | `web_search` with `include: ["web_search_call.action.sources"]`. Use **only** URLs from `url_citation`/sources, never facts from the answer text | mini (verify quality vs full, §4) |
| Triage (is it a hackathon? open? candidate-worthy?) | Yes, on title + snippet + structured hints, JSON schema output, ≤ 1k tokens | nano/mini |
| Extraction | Existing V1.2 extractor (evidence-checked) | mini; full model retry only on `llm_error`/conflict |
| Relevance scoring | **No LLM.** Deterministic rules on extracted fields (§3.4) | — |
| Dedup | V1.3: exact → fuzzy; LLM only for flagged pairs | full (few calls) |
| Verification | **No LLM.** Tier 1/2 evidence + admin (unchanged rule) | — |

## 3. Pipeline architecture

```text
discover ─► candidate (URL + hints) ─► normalize + dedup (V1.3) ─► triage ─► fetch (SafeFetcher)
        ─► extract (V1.2) ─► relevance score ─► draft event + evidence ─► admin review ─► publish
```

### 3.1 Tables (sketch, `app` schema, same RLS/grant pattern)

- `app.sources` (exists) **+** `adapter text` (registry key, e.g. `devpost_json`, `sitemap`,
  `list_page`, `announcement_ids`, `web_search`), `config jsonb` (URL patterns, filters),
  `check_interval interval`, `next_check_at`, `last_checked_at`, `etag`, `last_modified`,
  `list_hash`, `robots_checked_at`, `crawl_delay_s`, `consecutive_failures`, `last_item_count`.
- `app.runs` (exists): new `kind` values `discovery`, `web_search`; `stats` holds counts, tokens,
  and calls.
- `app.candidates`: `id, url, url_normalized unique, source_id, run_id, discovered_via
  ('adapter'|'sitemap'|'web_search'|'link'|'watchlist'|'bot_forward'|'community'),
  hints jsonb, status ('new'|'triaged_out'|'queued'|'fetched'|'drafted'|'duplicate'|'rejected'|
  'error'), triage jsonb, relevance_score smallint, relevance_reasons jsonb, event_id FK,
  content_hash, first_seen_at, last_seen_at, seen_count, next_fetch_at, attempts, last_error`.
  `hints` holds title/dates/location from the list or API, with provenance. Workers claim rows with
  `SELECT … FOR UPDATE SKIP LOCKED` (no Redis, matching the ROADMAP rejection list).
- `app.event_series`: `id, name, organizer, source_id, typical_month, last_event_id,
  watch_urls text[], expected_from, expected_to, status`.
- `app.event_field_evidence` (exists): add `source = 'adapter'` for API/JSON values (D-16
  provenance per field, with `run_id` + `event_source_id`).

### 3.2 Normalize and dedup
Exact `url_normalized` against `candidates`, `events.official_url_normalized` and
`event_sources.url_normalized` **before any fetch** (most daily candidates are re-sightings that
only bump `last_seen_at`). Then the V1.3 fuzzy title + date (+ organizer) match against events and
open candidates. Uncertain matches go to `duplicate_candidates`, never an automatic merge. A
platform page and an official site for the same event become two `event_sources`, not two events.

### 3.3 Fetch and politeness
SafeFetcher (SSRF, size, timeouts) + per-host token bucket (1 req / 5 s, or robots `Crawl-delay`
if larger), robots.txt via `urllib.robotparser` cached 24 h (fail closed on 5xx), conditional
GET (`If-None-Match`/`If-Modified-Since`), list-page content hash on the item region only (not
the full page with ads/CSRF tokens), back-off after 3 failures, max N new detail fetches per
source per run. UA already carries a contact URL (`common/http.py`). Never fetch through bot
walls, logins, or `Disallow`ed APIs (Coderspace `/events/api/`).

### 3.4 Relevance score (explainable, deterministic)
Stored as `relevance_reasons = [{rule, points, evidence_field}]`. Hard rejects first:
deadline/end in the past; eligibility excludes Türkiye or non-members (Devpost `invite_only`,
"US residents only"); not a hackathon/ideathon/game jam/datathon. Then points: online & open
worldwide +25; in person in Elazığ/East Anatolia +30, elsewhere in Türkiye +15 (+5 travel/
accommodation support); abroad in person −20 unless travel grant; students/beginners explicitly
welcome +10; Turkish or English +5, otherwise −30; deadline ≥ 7 days away +10, < 3 days −10;
Tier 1/2 source +10, only Tier 4 → `needs_verification`. Thresholds: ≥ 40 → draft; 15–39 →
"low relevance" tab; < 15 → hidden but kept (recall audit).

### 3.5 Scheduling (V1.5)
The writer is the local FastAPI (D-05), so **Windows Task Scheduler** runs a CLI
(`uv run python -m fhc_api.discovery run --due`) daily and 2×/week for web_search, with "run task
as soon as possible after a scheduled start is missed", so a laptop that was off catches up.
Alternatively, in-process APScheduler while the API runs. GitHub Actions/Vercel Cron would need the
DB write credentials and the OpenAI key in the cloud and split the single writer, so not
recommended. They stay for keep-alive only (D-19). Overview digest: new drafts, sources with 0 items
or failures, tokens and calls per day.

### 3.6 Metrics
- **Gold list:** the owner and admin record every relevant hackathon they see by any means over 4
  weeks (target ≥ 30; the legacy `events.json` has only 6). Recall = gold ∩ found / gold, **per
  strategy** (adapter vs watchlist vs search vs inbound). This shows whether search earns its cost.
- Precision = drafts accepted / drafts created, and triage false-negative audit on a 10% sample of
  `triaged_out`.
- Freshness = median(first_seen_at − the event's announcement date, when known).
- Cost = tokens/day by model class, `web_search` calls/day, from `runs.stats`.

## 4. Token budget (proposed cadence)

Assumptions: around 40 candidate sightings/day after URL dedup, of which about 12 are new and
pass triage. Extraction input is up to 24 000 chars (about 7k tokens; Turkish runs higher) + prompt
and schema (about 2k) + output (about 1k), so roughly **10k tokens per page**.

| Item | Per day | Class |
|---|---|---|
| Triage 40 × 1k | 40k | nano/mini |
| Extraction 12 × 10k | 120k | mini |
| Retry/conflict 3 × 12k | 36k | full |
| web_search sweep: 10 queries 2×/week (about 3/day), about 10k search content tokens each (third-party measurement, unverified) | about 30k + 3 calls | mini or full |
| Dedup LLM on flagged pairs, 5 × 2k | 10k | full |
| **Total** | **about 160k mini + about 50–80k full** | |

That is within 2.5M (mini) and 250k (full) per day **if** those caps apply to our org and models.
Peak days (a Teknofest season or a first backfill run of 300 URLs ≈ 3M) must be **rate-capped**
(max extractions/day setting) or spread over days.

Caveats (verify before relying on "free"):
- OpenAI's complimentary-token program is tied to **sharing API inputs/outputs with OpenAI** and
  is per-org and per-tier. The public post lists older model groups (gpt-4o, gpt-4.1, o-series /
  mini variants) and gives no end date (30 days' notice)
  ([community post](https://community.openai.com/t/good-news-extended-free-tokens-on-traffic-shared-with-openai/1241322)).
  Confirm in the org's Data Sharing settings which current models qualify.
- `web_search` **calls** are billed separately ($10 / 1k). Whether search content tokens count
  against free tokens is unverified. At 3 calls/day that is about $1/month.
- Data sharing means page text goes to OpenAI for training. Fine for public event pages; **never** send
  community/team application data (D-22) through a data-sharing project. Use a separate OpenAI
  project without sharing for anything personal.
- Fallback when the caps are hit: stop extraction for the day (queue persists), or the local Ollama model.

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **ToS**: Devpost ToS forbids automated access despite permissive robots; Luma "publicly supported interfaces only"; Meta/LinkedIn/Telegram forbid scraping | Per-source `tos_status` in `sources.notes`; Devpost adapter **disabled until written permission** (email support; owner decision). Meanwhile use dev.events/web_search for discovery and admin-triggered imports. Social and Telegram content via forward-to-bot only |
| Prompt injection in pages, search snippets and search answers | Untrusted envelope (exists); the search call has only the search tool; we take only URLs from citations, then re-fetch and extract ourselves; triage/extraction calls have **no tools**; outputs schema-validated; `looks_like_instruction` evidence check (exists); LLM never sets status/verification |
| Hallucinated events | No event exists without a fetched page; every field needs a snippet found in that page (V1.2 evidence check); web_search answer text is discarded |
| Stale events | Hard reject on past deadline; re-check `next_fetch_at` for drafted/published events weekly (`event_sources.last_checked_at`, `content_hash`), and V1.3 revisions show changes; series watchlist keeps "2025" pages from being imported as new |
| Duplicates (platform vs official, TR vs EN title, yearly editions) | URL dedup before fetch; V1.3 fuzzy + date; series link; uncertain → manual merge |
| Adapter rot (redesigns) | Alarm when `last_item_count` drops to 0 or parse errors; fixtures per adapter in tests |
| Queue flood / admin fatigue | Relevance threshold, daily cap, "low relevance" tab, weekly digest instead of per-item bot pings |
| Cost drift | Daily token/call counters in `runs.stats`; hard caps in settings |
| Being blocked | Polite rate, conditional GET, honour 429/`Retry-After`, never rotate IPs/UAs |

## 6. Version plan

**Order: keep V1.2 → V1.3 → V1.4 → V1.5** (D-11 reasoning still holds: automated discovery
without dedup floods review). Two small changes: (1) start the **gold list now** (owner task, no
code) because recall needs a 4-week baseline; (2) move the **web_search sweep** from "Later" into
V1.4c, because the free cap makes it affordable, while keeping it a supplement.

| Version | Milestones | Done when |
|---|---|---|
| V1.2 (now) | Finish URL import; switch the provider to OpenAI (new `LLMProvider`, keep the Ollama fallback); benchmark rerun on the 20 pages | Benchmark field accuracy ≥ the Ollama baseline; tokens/page logged in `runs.stats` |
| V1.3 | Dedup (exact → fuzzy → LLM on pairs), `duplicate_candidates`, `event_revisions`, merge UI. **Design the matcher to accept a candidate (URL + hints)**, not only events | ≥ 95% of seeded duplicate pairs flagged and 0 automatic merges on uncertain pairs (test set) |
| V1.4a | `candidates` table + queue; adapter framework (robots, rate limit, conditional GET, hash); adapters: Coderspace, Techcareer, dev.events, Youthall, lablab, Fırat announcements; "Run now" per source; relevance score + reasons in review | 6 adapters with fixture tests; a re-run creates 0 new candidates for unchanged sources; ≥ 70% gold recall from adapters alone |
| V1.4b | Series watchlist (`event_series`, predict window, create from an accepted event); forward-to-bot → candidate; Teknofest seasonal adapter; Devpost adapter (enabled only if permission is granted) | Watchlist predicts ≥ 1 real new edition; a forwarded link becomes a candidate in < 1 min |
| V1.4c | web_search sweep (TR+EN templates, citations only, source suggestions); one-hop link expansion; metrics page (recall per strategy, precision, tokens) | Combined recall ≥ 90% of gold; precision ≥ 60% accepted drafts; tokens within §4 caps for 7 days |
| V1.5 | Task Scheduler/APScheduler with catch-up, per-source intervals, daily caps, Overview digest + failure alarms | 14 consecutive days of unattended runs, no cap breach, alarms fire on a forced adapter failure |

## 7. Open questions for the owner

1. Email Devpost for permission to poll the hackathon list (1 request/day), or exclude Devpost
   automation entirely?
2. OK to enable OpenAI data sharing on a dedicated "discovery" project (public pages only)?
   Which tier is the org (the caps differ by tier)?
3. Geographic scope for in-person events: Türkiye-wide, or prioritise East Anatolia?
4. Include ideathons, datathons, game jams, Teknofest-style competitions, or only hackathons?
5. Who maintains the gold list for 4 weeks, and which Telegram/WhatsApp/Instagram channels do
   admins follow (for forward-to-bot)?
6. Daily review budget: how many drafts per day is acceptable (sets the threshold and cap)?

## Sources (accessed 2026-10-13)

- robots.txt (fetched): coderspace.io, youthall.com, techolay.net, teknofest.org, kariyer.net,
  luma.com, eventbrite.com, meetup.com, devpost.com, mlh.com, devfolio.co, hackathon.com,
  unstop.com, taikai.network, lablab.ai, linkedin.com, instagram.com, patika.dev, firat.edu.tr,
  tubitak.gov.tr, techcareer.net, dev.events (each at `https://<host>/robots.txt`)
- Sitemaps: https://coderspace.io/sitemap-events.xml · https://www.techcareer.net/sitemap-events.xml ·
  https://www.youthall.com/sitemap.tr-events.xml · https://teknofest.org/tr/sitemap.xml ·
  https://lablab.ai/sitemap.xml · https://taikai.network/sitemap.xml
- Endpoints/pages: https://devpost.com/api/hackathons?status[]=open ·
  https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons ·
  https://dev.events/hackathons/AS/TR · https://dev.events/rss.xml ·
  https://www.mlh.com/seasons/2027/events · https://luma.com/istanbul ·
  https://www.eventbrite.com/d/turkey/hackathon/ · https://dorahacks.io/api/hackathon/ ·
  https://www.firat.edu.tr/tr · https://tubitak.gov.tr/tr/duyuru · https://index.commoncrawl.org/collinfo.json
- Terms: https://info.devpost.com/terms · https://luma.com/terms · https://telegram.org/tos ·
  https://coderspace.io/kullanicisozlesmesi
- OpenAI: https://developers.openai.com/api/docs/pricing ·
  https://developers.openai.com/api/docs/guides/tools-web-search ·
  https://community.openai.com/t/good-news-extended-free-tokens-on-traffic-shared-with-openai/1241322
- Search APIs: https://brave.com/search/api/ · https://exa.ai/pricing ·
  https://docs.tavily.com/documentation/api-credits · https://serpapi.com/pricing ·
  https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement ·
  https://brave.com/learn/google-api-shutdown/
- Search-content token measurement (third party, unverified):
  https://parallel.ai/articles/openai-responses-agents-how-to-choose-the-right-web-search-backend
