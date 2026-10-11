# V1.2: URL Import and Extraction

Goal: the admin pastes a hackathon URL and gets a **draft** event with the fields filled in and
the supporting snippet shown beside each field. A human still reviews and publishes (D-11,
AI_ARCHITECTURE: "AI proposes, code decides, a human approves").

## Flow

```text
Admin "Import from URL" ─► POST /imports/url {url}
  1. normalize_url → exact match on events.official_url_normalized → existing event? return it
  2. PageLoader.load_page(url)      SafeFetcher → selectolax (JSON-LD Event, OpenGraph, meta)
                                    → trafilatura main text (≤ 24 000 chars)
  3. Extractor.extract(page)        LLM (Ollama, schema-constrained, untrusted envelope)
                                    → Pydantic validation → evidence check → rules
                                    → merge: JSON-LD/meta win; disagreement = "conflict" flag
  4. create draft event (+ event_sources 'official', + event_field_evidence rows, + run row)
  5. → admin opens the event's review page: each field with its source and snippet; flags
```

The types between the steps are in `services/api/src/fhc_api/importing/models.py`.

## Parts and ownership

| Part | Files | Notes |
|---|---|---|
| A. Page loading | `importing/page.py`, tests with HTML fixtures | `selectolax`, `trafilatura` (new deps). Uses `common/http.SafeFetcher` (body read, HTML only for import). JSON-LD: `Event` and subtypes (`Hackathon` is not a schema.org type; also accept `@graph`, arrays, `EducationEvent` etc.). Dates: ISO 8601 → date in Europe/Istanbul when a time zone is given. `location` → venue/city/country (`Place`, `PostalAddress`, `VirtualLocation` → online). `eventAttendanceMode` → format. every priced offer `price == 0` (or `isAccessibleForFree`) → `is_free`. |
| B. Extraction | `importing/extraction.py`, `importing/prompts.py`, tests with a fake provider | Schema per field `{value, snippet}`; `wrap_untrusted` + `build_system_prompt`; Turkish dates ("5 Ekim'e kadar") resolved with the fetch date for the year; evidence check on normalized text; rules: `start ≤ end`, `deadline ≤ end`, team `1 ≤ min ≤ max ≤ 20`, URLs http(s), years within fetch year −1 … +2. The LLM never sets verification status. LLM failure → structured fields only, `llm_error` set. |
| C. Benchmark | `services/api/bench/` (harness, committed); page snapshots and gold files in `services/api/bench/data/` (**gitignored**, third-party pages) | 20 pages (6 legacy + 7 Devpost + 7 Turkish). Gold drafted by the agent, marked `needs_owner_check`. Models per LOCAL_LLM_RESEARCH §2–3 (≤ 4, ≤ 20 GB); verify each tag on ollama.com before `ollama pull`. Report in `docs/research/LLM_BENCHMARK.md`. |
| D. Data, API, admin | migration (`app.runs`, `app.event_field_evidence`), `importing/service.py`, `importing/router.py`, admin "Import from URL" page and evidence on the review page | Built against the Protocols with fakes; wired to A and B at integration. |

## Data (part D)

- `app.runs`: `id, kind ('url_import'), status ('running'|'succeeded'|'failed'), input jsonb
  ({url}), stats jsonb (durations, field counts, flags, extracted_by), error text, event_id
  (nullable FK), started_at, finished_at`.
- `app.event_field_evidence`: `id, event_id, field, value_text, source ('jsonld'|'meta'|'llm'|
  'manual'), extracted_by, snippet, flag (nullable FlagKind), flag_detail, run_id,
  event_source_id, extracted_at`. One row per proposed or flagged field; history is kept
  (new import = new rows; the review page shows the latest run).
- Same RLS/grant pattern as the other `app` tables (admin_backend only).

## Decisions

- Synchronous request (the admin waits; the LLM cold start is up to ~60 s). The API timeout
  for this call is long; the admin shows progress text.
- Duplicate check in V1.2 is the exact normalized URL only; fuzzy dedup is V1.3.
- No image download (og:image is only stored as a suggestion in `stats`, not as `poster_url`).
- No Playwright in V1.2. A JS-only page gives a clear "no readable content" error.

## Part D as built

- Migration `20261012120000_url_import.sql`. `event_field_evidence` stores one row per kept
  value and one row per flag (`value_text`/`source` null on a flag-only row), because a
  field can carry a value and several flags; `field` is a column-name check, not an enum.
- `POST /imports/url` (`import_event_url`) → `{outcome: created|duplicate, event_id, run}`;
  409 when no PageLoader/Extractor is set (the real app uses `create_app(url_import=True)`),
  422 for an invalid/private URL (no run) or a `PageError` (run `failed`).
  `GET /imports/runs` (`list_import_runs`), `GET /events/{id}/evidence`
  (`get_event_evidence`, latest run, grouped per field, `matches_current`).
- `official_url` = the final URL after a same-site redirect (same host ignoring `www.`),
  else the requested URL; the final URL is in `run.stats` (omitted when over 500 chars).
  Duplicates match `events.official_url_normalized` and `event_sources.url_normalized`:
  before the fetch (requested URL) and again in the write transaction (requested and
  final URL, one advisory lock per URL in sorted order, so imports sharing either URL
  serialize).
- Event source: role `official`, source "Manual entry" (as in the legacy import), URL =
  the page that was read (final URL). After a cross-site redirect it therefore differs
  from `events.official_url`; the column meaning ("a URL confirming the event") is
  unchanged.
- Values are validated again with the event field rules; cross-field conflicts drop the
  later field (`end_date`, `team_max`, `prize_pool`) with a `rule_violation` flag. Without
  a proposed title the page title is used (`meta` evidence), else "Imported from <host>".
- Audit: `url_import` on the created event (`run_id`, counts). Failed runs have no event
  and are visible in the run list only.
- Admin: `/events/import` (form + recent runs), "Import from URL" on the Events toolbar,
  and an "Imported fields" card on the review page. The admin waits up to 240 s.

## Known limits (part A)

- JS-only pages fail with "no readable content" even when their JSON-LD has usable
  structured values; returning structured-only results is not done in V1.2.
- Fetch timeouts: 20 s per phase for imports and a 45 s wall-clock deadline across
  redirect hops; a very slow site (one test page took 75 s) still fails with
  "request timed out". DNS resolution has no timeout of its own.
- Charsets: only a fixed subset of WHATWG labels is honoured; others fall back to
  UTF-8, then cp1254. No statistical charset detection.
- `is_free` is set only when every priced offer is 0 or `isAccessibleForFree` is true;
  `application_url` comes only from `offers.url` or a `RegisterAction` target.
