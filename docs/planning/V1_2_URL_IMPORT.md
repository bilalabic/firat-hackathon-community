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
| A. Page loading | `importing/page.py`, tests with HTML fixtures | `selectolax`, `trafilatura` (new deps). Uses `common/http.SafeFetcher` (body read, HTML only for import). JSON-LD: `Event` and subtypes (`Hackathon` is not a schema.org type; also accept `@graph`, arrays, `EducationEvent` etc.). Dates: ISO 8601 → date in Europe/Istanbul when a time zone is given. `location` → venue/city/country (`Place`, `PostalAddress`, `VirtualLocation` → online). `eventAttendanceMode` → format. `offers.price == 0` → `is_free`. |
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

## Known limits (part B, deferred)

- Country and currency codes are checked by pattern (`^[A-Z]{2}$`, `^[A-Z]{3}$`) and a small
  name/symbol map, not against the full ISO 3166 / ISO 4217 lists.
- A snippet may come from `page.title` as well as the main text (the model sees both).
- Numeric dates are read as day-month-year (`10.12.2026`) or ISO; US month/day order is not
  recognized.
- The extraction schema sent to Ollama uses `$defs`/`$ref`; not inlined, not yet checked with
  every candidate model.
