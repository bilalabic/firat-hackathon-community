# Roadmap

## Revised version sequence

The provisional sequence placed Discovery (V1.1) before Deduplication (V1.2), Extraction (V1.3) and Telegram (V1.4). After inspection, it is **reordered**:

| Version | Content | Why here |
|---|---|---|
| **V1** | Foundation (see MVP.md) | — |
| **V1.1** | **Telegram publishing**: preview (caption + OG card), send, store `message_id`, edit-on-change, publication history | Small, well-documented API; immediate value with manually entered events; exercises the publication model early |
| **V1.2** | **URL import + extraction**: paste URL → safe fetch → JSON-LD/meta → LLM extraction with evidence → draft; LLM benchmark; `runs`, `event_field_evidence` | Fixes the real bottleneck (stale data since 2026-08-17) with no crawling-policy risk |
| **V1.3** | **Deduplication + event history**: exact → RapidFuzz / `pg_trgm` → LLM only for flagged pairs; `duplicate_candidates`; `event_revisions`; merge UI (never automatic for uncertain matches) | Must exist **before** automated discovery floods the queue |
| **V1.4** | **Curated source discovery**: `sources` with retrieval methods (Devpost JSON, organizer pages), manual "run now", robots and rate limits | Needs dedup and extraction in place |
| **V1.5** | **Scheduled discovery**: Windows Task Scheduler (or in-process APScheduler while the admin runs) triggering V1.4 runs; digest in Overview | Automation last, once each step is trusted |
| **V2** | Public site: organizer pages, calendar export (ICS), email/Telegram digest subscription, better search; community workflows (application follow-up, team matching board, read-only) | Product growth after the pipeline is stable |
| **Later** | WhatsApp (official API requirements not yet researched; manual posting until then), Instagram, search-API-based discovery, Supabase Storage for posters, multi-admin auth | Only on demonstrated need |

Moving Telegram earlier is recorded as decision D-11.

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
| Cloud LLM provider | V1.2+ (optional) | Only if local quality fails the benchmark |
| Fuzzy/semantic dedup, revisions | V1.3 | |
| Source discovery / scheduling | V1.4 / V1.5 | |
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
