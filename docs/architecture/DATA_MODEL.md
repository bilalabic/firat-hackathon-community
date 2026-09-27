# Data Model

Database: Supabase Postgres. Schema source: `supabase/migrations/*.sql` only.

## 1. Schemas

| Schema | Exposed via Data API | Contents |
|---|---|---|
| `app` | **No** | All tables. RLS enabled on every table with **no policies for `anon`/`authenticated`** (defense in depth) |
| `api` | **Yes** (the only exposed schema; `public` is removed from exposed schemas) | `events_public` view; functions `submit_community_application`, `submit_team_application`, `keep_alive` |

The FastAPI backend connects as a dedicated Postgres role `admin_backend` (not `postgres`) with DML rights on `app`. DDL is done only by migrations.

## 2. Enums

```sql
create type app.event_status as enum ('draft','in_review','approved','published','archived','rejected');
create type app.verification_status as enum ('unverified','partially_verified','verified');
create type app.event_format as enum ('in_person','online','hybrid');
create type app.source_role as enum ('official','registration','discovery','announcement');
create type app.publication_platform as enum ('telegram');          -- 'whatsapp' etc. added later
create type app.publication_status as enum ('draft','sent','edited','deleted','failed');
create type app.application_status as enum ('new','contacted','accepted','declined','spam');
```

## 3. V1 tables

### `app.events`

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK default `gen_random_uuid()` | |
| `slug` | `text` unique, `^[a-z0-9]+(-[a-z0-9]+)*$`, ≤ 80 | Generated from title (port of `slugify`) |
| `title` | `text` not null, 3–160 | |
| `organizer` | `text` null, ≤ 160 | |
| `summary` | `text` null, ≤ 300 | Card text |
| `description` | `text` null, ≤ 5000 | Detail page (plain text / limited Markdown) |
| `categories` | `text[]` default `{}` | Controlled vocabulary in code (e.g. `ai`, `fintech`, `web3`, `energy`) |
| `technologies` | `text[]` default `{}` | Free tags, lower-case |
| `format` | `app.event_format` null | |
| `city`, `country` | `text` null; `country` = ISO 3166-1 alpha-2 | Replaces free-text `location` |
| `venue` | `text` null | |
| `start_date`, `end_date` | `date` null; check `end_date >= start_date` | **New `end_date`** fixes multi-day bug |
| `application_deadline` | `date` null | Inclusive; interpreted in `timezone` |
| `timezone` | `text` not null default `'Europe/Istanbul'` | IANA name |
| `eligibility` | `text` null, ≤ 500 | |
| `team_min`, `team_max` | `smallint` null; `1 ≤ min ≤ max ≤ 20` | Replaces `teamSize` text |
| `prize_pool` | `numeric(12,2)` null | |
| `currency` | `char(3)` null (ISO 4217) | Required if `prize_pool` set |
| `is_free` | `boolean` null | `null` = unknown |
| `official_url` | `text` not null, `^https?://` | |
| `official_url_normalized` | `text` not null, indexed | host without `www.`, lower-cased, no trailing slash, tracking params removed |
| `application_url` | `text` null, `^https?://` | |
| `poster_url`, `banner_url`, `organizer_logo_url` | `text` null, `^https://` | External or Supabase Storage (later) |
| `status` | `app.event_status` not null default `'draft'` | |
| `verification_status` | `app.verification_status` not null default `'unverified'` | |
| `duplicate_of` | `uuid` null FK → events | Set when resolved as duplicate (V1.3) |
| `internal_notes` | `text` null | **Never exposed** |
| `created_at`, `updated_at` | `timestamptz` | `updated_at` via trigger |
| `discovered_at`, `verified_at`, `published_at`, `archived_at` | `timestamptz` null | |

Constraint: `status = 'published'` requires `title`, `official_url`, and `start_date` to be non-null (check constraint). FastAPI enforces richer rules.

### `app.sources`

`id, name, kind (organizer_site|event_platform|social|aggregator|university|community|manual), tier smallint 1–4, base_url, retrieval_method (manual|api|json_endpoint|rss|html|browser), enabled bool, requires_js bool, notes, created_at, updated_at`.

V1 uses it for manual attribution only (seeded with "Manual entry" and platform rows for Devpost and Patika).

### `app.event_sources`

`id, event_id FK, source_id FK null, url, url_normalized, role app.source_role, first_seen_at, last_checked_at, last_http_status smallint null, content_hash text null`, with `unique(event_id, url_normalized)`.

This is **event-level provenance**: which pages back this event and in what role. The Review screen uses it.

### `app.publications`

| Column | Notes |
|---|---|
| `id` | |
| `event_id` FK | |
| `platform` | `telegram` |
| `target` | chat id / `@channel` |
| `external_id` | Telegram `message_id` (text, unique per platform + target) |
| `content_hash` | SHA-256 of the **publishable projection** of the event (title, dates, deadline, format, city, URLs) at send time |
| `content_version` | int, increments on each edit |
| `body` | Exact text sent |
| `image_url` | Exact image URL sent |
| `status` | `app.publication_status` |
| `sent_at`, `edited_at`, `deleted_at` | |
| `error` | Last error message (no tokens) |

"Changed since published" = the event's current publishable hash ≠ the latest `sent`/`edited` publication's `content_hash`. It needs no revision table. The table is created in V1 (empty), and V1.1 writes to it.

### `app.community_applications`

`id, full_name (≤120), university (≤160), field_of_study (≤120), year_of_study (text: 'prep','1'..'6','graduate','alumni','other'), interests text[] (≤10), experience_level ('none','beginner','intermediate','advanced'), looking_for (≤500), preferred_channel ('telegram','whatsapp'), telegram_username (^[A-Za-z0-9_]{5,32}$, null), phone (E.164, null; required only when preferred_channel='whatsapp'), message (≤1000), consent_version text not null, consented_at timestamptz not null, status app.application_status default 'new', created_at`.

### `app.team_applications`

`id, full_name, affiliation, areas text[] (frontend|backend|ai_automation|design|content|community|research), skills (≤500), github_url, linkedin_url, availability ('1-3h','4-7h','8h+' per week), motivation (≤1000), consent_version, consented_at, status, created_at`.

No IP addresses or user agents are stored (data minimisation).

### `app.heartbeats` (keep-alive monitoring, D-19)

`source text primary key check (source in ('vercel_cron','github_actions'))`, `last_seen_at timestamptz not null`. (There is no counter, so the operation stays idempotent.)

Written only by `api.keep_alive(source text)`: an upsert of `last_seen_at = now()` for an allowed source, followed by a real read (`select count(*) from app.events where status = 'published'`), returning that count. An unknown source fails with `23514`. The worst abuse through the publishable key is refreshing a timestamp. The admin Overview reads this table via FastAPI.

## 4. The `api` surface (the only thing the public can touch)

```sql
-- Read: published, non-duplicate events, public columns only.
create view api.events_public as
  select id, slug, title, organizer, summary, description, categories, technologies,
         format, city, country, venue, start_date, end_date, application_deadline, timezone,
         eligibility, team_min, team_max, prize_pool, currency, is_free,
         official_url, application_url, poster_url, banner_url, organizer_logo_url,
         verification_status, published_at, updated_at
  from app.events
  where status = 'published' and duplicate_of is null;
-- Owned by a role that can read app.events; security_invoker is NOT set on purpose:
-- the view is the filter. anon gets SELECT on the view only.
grant usage on schema api to anon;
grant select on api.events_public to anon;

-- Write: validated insert, returns nothing readable.
create function api.submit_community_application(payload jsonb) returns void
  language plpgsql security definer set search_path = '' as $$ ... $$;
revoke all on function api.submit_community_application(jsonb) from public;
grant execute on function api.submit_community_application(jsonb) to anon;
```

Why functions instead of an `INSERT` policy: the function validates and normalizes. The table shape stays hidden, `anon` never gets any table privilege, and the function returns nothing, so no data can be read back.

Supabase's security advisor flags security-definer views and functions. These two are intentional and are documented here. pgTAP tests (`supabase/tests/`) must assert:
1. `anon` cannot `select` from any `app.*` table.
2. `api.events_public` returns no `draft`/`in_review`/`approved`/`archived`/`rejected` rows.
3. `anon` can execute the submit functions, cannot read the rows back, and invalid payloads raise errors.
   `anon` can execute `api.keep_alive` only with an allowed source name.
4. `internal_notes` is not a column of `api.events_public`.

## 5. Deferred tables

| Table | Version | Purpose |
|---|---|---|
| `app.event_field_evidence` | V1.2 | Field-level provenance: `event_id, field, value_text, event_source_id, snippet, extracted_by ('llm:<model>'|'jsonld'|'manual'), extracted_at`. Justified once extraction exists: the Review UI shows the snippet beside each field |
| `app.event_revisions` | V1.3 | Append-only snapshots (`event_id, revision, changed_fields text[], snapshot jsonb, changed_at, reason`) |
| `app.duplicate_candidates` | V1.3 | `event_a, event_b, level ('exact','fuzzy','semantic'), signals jsonb, decision ('definite','possible','not_duplicate','pending')` |
| `app.runs` | V1.2 | Pipeline run log: `kind, started_at, finished_at, status, stats jsonb, error` |
| `app.assets` | Later | Only if Supabase Storage is used for posters |

## 6. Legacy import mapping (`events.json` → `app.events`)

| Legacy | New | Rule |
|---|---|---|
| `id` | `slug` | as-is (already slug-shaped) |
| `name` | `title` | |
| `organizer` | `organizer` | |
| `deadline` | `application_deadline` | |
| `eventDate` | `start_date` | `end_date` = null; owner fills in the admin |
| `location` | `city`/`country` | Manual mapping table in the import script (6 rows); `"Online"` → null |
| `format` | `format` | `Yüz yüze`→`in_person`, `Online`→`online`, `Hibrit`→`hybrid` |
| `teamSize` | `team_min`/`team_max` | Regex `(\d+)-(\d+)` or `(\d+)`; `Belirtilmemiş` → null |
| `description` | `description` (and `summary` = first sentence ≤ 300) | |
| `url` | `official_url` | + `event_sources` row, role `official`, source "Manual entry" |
| — | `status` | `published` (they are public today); `verification_status` = `unverified` |
