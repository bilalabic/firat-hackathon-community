# V1 (MVP Foundation)

## Goal

Replace `events.json` + Issue Forms with a shared database, a local admin, and a Vercel public site. The public site must work while the laptop is off. Prepare (but do not yet run) Telegram and LLM features.

## In scope

| # | Capability |
|---|---|
| 1 | Monorepo: `apps/web`, `apps/admin`, `services/api`, `supabase/` with one `pnpm dev` |
| 2 | Supabase schema (`app` + `api`), RLS, privilege tests, reproducible migrations, seed from legacy data |
| 3 | FastAPI: events CRUD + state machine, sources, event sources, community/team application reads, review signals, health checks |
| 4 | Admin UI on dashboard-01: Overview, Events, Review, Community Applications, Contributions, Sources, Settings |
| 5 | Public site: home, hackathon list with 4 phases + search/filters, event detail with SEO + OG card, community page + form, contribute page + team form, about, sitemap/robots |
| 6 | On-demand revalidation from API → web |
| 7 | `publications` table + publishable-hash function (no sending yet) |
| 8 | Telegram config check (`getMe`, `getChat`, bot admin rights) |
| 9 | LLM provider interface + Ollama health/structured test |
| 10 | Legacy cutover: data imported, Pages → redirect page, Issue Form automation retired |
| 10a | Supabase keep-alive: Vercel Cron + GitHub Actions + heartbeat in admin (D-19) |
| 11 | English documentation that matches reality |

## Explicitly excluded from V1

Telegram sending (V1.1) · URL import / extraction (V1.2) · fuzzy/semantic dedup and revisions (V1.3) · automated discovery and schedules (V1.4–1.5) · public user accounts · admin authentication beyond local token · WhatsApp/Instagram automation · image generation models · Supabase Storage uploads · Turnstile/captcha (unless spam appears) · shared `packages/` · Docker for app services · analytics dashboards/charts.

## Acceptance criteria

Each criterion is checked by a named test or a manual step recorded in the milestone log.

**Repository and setup**
1. `git status` is clean after a fresh clone + setup. `.gitignore` covers all env files, and `git ls-files | grep -E '\.env($|\.)' ` returns only `.env.example` files.
2. From a fresh clone, following README only: `pnpm install`, `uv sync`, `pnpm supabase start`, `pnpm supabase db reset`, `pnpm dev` starts web :3000, admin :3001 and API :8000 without errors.
3. `pnpm lint`, `pnpm typecheck`, `pnpm build` (web + admin) pass. In `services/api`, `ruff check`, `ruff format --check`, `mypy`, `pytest` pass. `pnpm supabase test db` passes.

**Database and security**
4. Migrations apply cleanly to an empty local DB and to the cloud project. `db reset` is repeatable.
5. pgTAP: `anon` cannot select any `app.*` table. `api.events_public` returns only `published`, non-duplicate events. `internal_notes` is not exposed. Submit functions accept valid payloads, reject invalid ones, and cannot be used to read data.
6. Manual check with `curl` and the publishable key against the cloud project: `GET /rest/v1/community_applications` fails, `GET /rest/v1/events_public` (Accept-Profile: `api`) returns published rows only, and a request **without** `apikey` is rejected (401). The local stack returned 200 without a key in M2; it only exposes public data, but the cloud behavior must be confirmed.
7. The API rejects requests without a bearer token (401) and with a foreign `Host` header (400) (pytest).
8. No secret appears in the web client bundle: build output grep for `sb_secret`, `postgres://`, the bot token prefix → none.

**Admin workflow**
9. Admin can create an event, edit it, submit for review, see review signals, approve, publish, unpublish and archive. Invalid transitions return 409 and are not shown as buttons (pytest for every transition + manual UI pass).
10. Admin lists community and team applications and changes their status.
11. Settings page shows DB OK. For Ollama it shows OK, "not running" or "model missing". For Telegram it shows OK / invalid token / bot not admin, or "not configured". Each state is a clear message (manual, with Ollama stopped and started).

**Public site**
12. Published events appear on the Vercel site within 10 s of publishing when revalidation succeeds, and within `cacheLife` if the call fails. Draft, in-review, approved, rejected and archived events never appear (manual + pgTAP 5).
13. With the laptop off (API and admin stopped), the public site serves lists and detail pages, and forms submit successfully.
14. Phase logic unit tests cover: open, closing-soon boundary (7/8 days), multi-day event in progress (Upcoming, not Past), undated, and deadline today (still open).
15. A form submission creates exactly one row. A honeypot or too-fast submission creates none. The success response contains no stored data.
16. Event detail page has title/description/canonical/OG image/JSON-LD. OG image renders Turkish characters correctly. `sitemap.xml` lists published events only.
17. Lighthouse (mobile) on `/hackathons`: Performance, Accessibility and SEO ≥ 95.

**Availability (D-19)**
21. Vercel Cron and the GitHub Actions keep-alive each produce a heartbeat row on the production project (checked after the first scheduled run of each). A manual `workflow_dispatch` also succeeds. The admin Overview shows both timestamps and marks a source red when older than 48 h (tested by editing a timestamp locally). `/api/cron/keep-alive` without the correct bearer returns 401.

**Migration**
18. All 6 legacy events are imported with correct mapping (script test compares counts and fields).
19. The old Pages URL shows a page linking to the new site. The Issue Form no longer adds events (workflow removed, template removed or redirected).

**Docs**
20. README and `docs/` describe the actual setup. A reviewer following them reproduces criteria 2–3.
