# Roadmap

## Revised version sequence

The provisional sequence placed Discovery (V1.1) before Deduplication (V1.2), Extraction (V1.3) and Telegram (V1.4). After inspection, it is **reordered**:

| Version | Content | Why here |
|---|---|---|
| **V1** | Foundation (see MVP.md) | — |
| **V1.1** | **Telegram publishing**: preview (caption + OG card), send, store `message_id`, edit-on-change, publication history | Small, well-documented API; immediate value with manually entered events; exercises the publication model early |
| **V1.2** | **URL import + extraction**: paste URL → safe fetch → JSON-LD/meta → LLM extraction with evidence → draft; LLM benchmark; `runs`, `event_field_evidence`. **Plus the OpenAI provider** (`OpenAIProvider`, Responses API over httpx2, `PIIGuard`, daily token budget; Ollama stays as fallback, D-23) and the **OpenAI benchmark** on the same 20 pages (`gpt-5.4-mini` default candidate vs `gpt-4.1-mini`, `gpt-4o`/`gpt-5.4` as ceiling) | Fixes the real bottleneck (stale data since 2026-08-17) with no crawling-policy risk |
| **V1.3** | **Deduplication + event history**: exact → RapidFuzz / `pg_trgm` → LLM only for flagged pairs; `duplicate_candidates`; `event_revisions`; merge UI (never automatic for uncertain matches). The matcher is **candidate-aware**: it accepts a URL + hints, not only events, so V1.4 can dedup before fetching. **Event types** (D-25): `app.event_type` enum (hackathon, ideathon, datathon, game jam, competition) + `events.event_type`, in `api.events_public`, the extractor, admin filter + form, public type filter, Telegram caption label; the public listing moves to `/etkinlikler` ("Etkinlikler", permanent redirect from `/hackathonlar`) | Must exist **before** automated discovery floods the queue; types are needed before discovery brings non-hackathons |
| **V1.4a** | **Discovery core** ([V1_4_DISCOVERY](V1_4_DISCOVERY.md), D-24): `candidates` queue, source adapter columns, adapter framework (robots, rate limit, conditional GET, hash); adapters Coderspace, Techcareer, dev.events, Youthall, lablab, Fırat announcements, Devpost (owner-accepted ToS risk, `DEVPOST_ENABLED` kill switch); triage, relevance score + reasons, daily draft cap; "Run now" | Needs dedup and extraction in place |
| **V1.4b** | **Watchlists + inbound**: `event_series`, admin-bot forwarded links and community suggestions → candidates; Teknofest, Kaggle, Patika, Unstop, MLH adapters | Recurring and social-only events |
| **V1.4c** | **Gap-finding**: OpenAI `web_search` sweep 2×/week (paid, citation URLs only), source suggestions, one-hop link expansion, metrics page (recall per strategy) | Measures what the adapters miss |
| **V1.5** | **Scheduled discovery** (D-26): Windows Task Scheduler on the local machine runs the discovery CLI (daily; web_search 2×/week) with "run as soon as possible after a missed start" (catch-up); no cloud runners (single writer, D-05); per-source intervals, caps, Overview digest + failure alarms | Automation last, once each step is trusted |
| **V2** | Public site: organizer pages, calendar export (ICS), email/Telegram digest subscription, better search; community workflows (application follow-up, team matching board, read-only) | Product growth after the pipeline is stable |
| **Later** | WhatsApp (official API requirements not yet researched; manual posting until then), Instagram, extra search APIs (Brave first, only if `web_search` is weak on Turkish queries), Supabase Storage for posters, multi-admin auth | Only on demonstrated need |

Moving Telegram earlier is recorded as decision D-11. The 2026-10-13 changes (OpenAI in V1.2, event types in V1.3, V1.4 split into a/b/c, Task Scheduler in V1.5) are D-23 to D-26, accepted in [DECISIONS](DECISIONS.md).

**Starts now, no code:** the discovery **gold list** (every in-scope event the owner and admins see, 4 weeks, target ≥ 30; V1_4_DISCOVERY "Metrics"). Recall in V1.4 is measured against it.

## Feature classification

| Feature | Class | Reason |
|---|---|---|
| Event CRUD, lifecycle, review signals (deterministic) | V1 | Core loop |
| Public listing, phases, detail, SEO, OG card | V1 | Replaces current site |
| Join Community / Join Team forms | V1 | Requested; replaces `mailto:` |
| Publication table + hash | V1 | Cheap now, costly to retrofit |
| Telegram send/edit/history | V1.1 | See above |
| Telegram invite links / join-request approval | V2 | Needs a community-operations decision first |
| URL import + LLM extraction | V1.2 | |
| Field-level provenance | V1.2 | Only useful once values come from extraction |
| Local LLM benchmark | V1.2 | Needed to choose the extraction model |
| Cloud LLM provider (OpenAI) | V1.2 | Default provider per D-23 (accepted); Ollama as fallback |
| Fuzzy/semantic dedup, revisions | V1.3 | |
| Event types + type filters (public, admin, Telegram label) | V1.3 | D-25 (accepted) |
| Source discovery (adapters, watchlists, inbound, web_search) / scheduling | V1.4a–c / V1.5 | D-24, D-26 (accepted) |
| Embeddings / vector DB | Later / Reject for now | Fuzzy + LLM-on-candidates is enough at our volume (hundreds of events) |
| Turnstile captcha | V1.x on demand | Only if spam appears |
| Admin charts/analytics | Reject (V1) | "Meaningless charts" are explicitly unwanted |
| Public user accounts, comments, chat | Reject | Not a social network |
| Hosting hackathons, applicant tracking, payments, sponsorship marketplace | Reject | Out of product scope |
| Generative images for event cards | Reject | Deterministic template instead |
| LangChain/LangGraph/CrewAI/AutoGen, LiteLLM | Reject (now) | Plain Python suffices |
| Redis, queues, Kafka, Kubernetes, microservices, GraphQL | Reject | No requirement |
| Local SQLite | Reject (V1) | Filesystem cache is enough for V1.2 |
| Docker for app services | Later (optional) | Only Supabase local uses Docker |
