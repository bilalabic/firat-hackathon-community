-- Core schema: all canonical tables live in `app`, which is NOT exposed by the Data API.
-- The only exposed schema is `api` (see supabase/config.toml and the next migration).
-- Design: docs/architecture/DATA_MODEL.md

-- ---------------------------------------------------------------------------
-- Default privileges: nothing new is ever auto-granted to API roles or PUBLIC.
-- ---------------------------------------------------------------------------
-- PUBLIC EXECUTE on functions is a built-in default; only a GLOBAL (not IN SCHEMA)
-- default-privilege revoke removes it for future functions in every schema.
alter default privileges for role postgres revoke execute on functions from public;
-- Supabase grants API roles everything on new objects in public; take all of it back.
alter default privileges for role postgres in schema public
  revoke all on tables from anon, authenticated, service_role;
alter default privileges for role postgres in schema public
  revoke all on sequences from anon, authenticated, service_role;
alter default privileges for role postgres in schema public
  revoke all on functions from anon, authenticated, service_role;

create schema app;
revoke all on schema app from public;

-- ---------------------------------------------------------------------------
-- Backend role. FastAPI connects as this role (never as postgres).
-- LOGIN + password are set per environment, outside migrations (see docs).
-- ---------------------------------------------------------------------------
create role admin_backend nologin noinherit;
alter role admin_backend set statement_timeout = '15s';
grant usage on schema app to admin_backend;
-- Future app tables are granted automatically; each still needs RLS + a policy
-- (enforced by supabase/tests/database/01_privileges.test.sql).
alter default privileges for role postgres in schema app
  grant select, insert, update, delete on tables to admin_backend;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
create type app.event_status as enum
  ('draft', 'in_review', 'approved', 'published', 'archived', 'rejected');
create type app.verification_status as enum
  ('unverified', 'partially_verified', 'verified');
create type app.event_format as enum ('in_person', 'online', 'hybrid');
create type app.source_kind as enum
  ('organizer_site', 'event_platform', 'social', 'aggregator', 'university', 'community', 'manual');
create type app.retrieval_method as enum
  ('manual', 'api', 'json_endpoint', 'rss', 'html', 'browser');
create type app.source_role as enum ('official', 'registration', 'discovery', 'announcement');
create type app.publication_platform as enum ('telegram');
create type app.publication_status as enum ('draft', 'sent', 'edited', 'deleted', 'failed');
create type app.application_status as enum ('new', 'contacted', 'accepted', 'declined', 'spam');

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
create function app.set_updated_at() returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table app.events (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique
    check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and length(slug) <= 80),
  title text not null check (length(btrim(title)) between 3 and 160),
  organizer text check (length(organizer) <= 160),
  summary text check (length(summary) <= 300),
  description text check (length(description) <= 5000),
  categories text[] not null default '{}' check (cardinality(categories) <= 10),
  technologies text[] not null default '{}' check (cardinality(technologies) <= 30),
  format app.event_format,
  city text check (length(city) <= 120),
  country char(2) check (country ~ '^[A-Z]{2}$'),
  venue text check (length(venue) <= 200),
  start_date date,
  end_date date,
  application_deadline date,
  timezone text not null default 'Europe/Istanbul' check (length(timezone) <= 64),
  eligibility text check (length(eligibility) <= 500),
  team_min smallint check (team_min between 1 and 20),
  team_max smallint check (team_max between 1 and 20),
  prize_pool numeric(12, 2) check (prize_pool >= 0),
  currency char(3) check (currency ~ '^[A-Z]{3}$'),
  is_free boolean,
  official_url text not null check (official_url ~ '^https?://' and length(official_url) <= 500),
  official_url_normalized text not null check (length(official_url_normalized) between 1 and 500),
  application_url text check (application_url ~ '^https?://' and length(application_url) <= 500),
  poster_url text check (poster_url ~ '^https://' and length(poster_url) <= 500),
  banner_url text check (banner_url ~ '^https://' and length(banner_url) <= 500),
  organizer_logo_url text check (organizer_logo_url ~ '^https://' and length(organizer_logo_url) <= 500),
  status app.event_status not null default 'draft',
  verification_status app.verification_status not null default 'unverified',
  duplicate_of uuid references app.events (id) on delete set null,
  internal_notes text check (length(internal_notes) <= 5000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  discovered_at timestamptz,
  verified_at timestamptz,
  published_at timestamptz,
  archived_at timestamptz,
  constraint events_dates_order check (end_date is null or start_date is null or end_date >= start_date),
  constraint events_team_order check (team_min is null or team_max is null or team_min <= team_max),
  constraint events_prize_currency check (prize_pool is null or currency is not null),
  constraint events_not_self_duplicate check (duplicate_of is null or duplicate_of <> id),
  constraint events_published_requires_start check (status <> 'published' or start_date is not null),
  constraint events_published_requires_published_at
    check (status <> 'published' or published_at is not null)
);

create index events_status_idx on app.events (status);
create index events_official_url_normalized_idx on app.events (official_url_normalized);
create index events_duplicate_of_idx on app.events (duplicate_of) where duplicate_of is not null;

create trigger events_set_updated_at
  before update on app.events
  for each row execute function app.set_updated_at();

create table app.sources (
  id uuid primary key default gen_random_uuid(),
  name text not null unique check (length(btrim(name)) between 2 and 120),
  kind app.source_kind not null,
  tier smallint not null check (tier between 1 and 4),
  base_url text check (base_url ~ '^https?://' and length(base_url) <= 500),
  retrieval_method app.retrieval_method not null default 'manual',
  enabled boolean not null default true,
  requires_js boolean not null default false,
  notes text check (length(notes) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger sources_set_updated_at
  before update on app.sources
  for each row execute function app.set_updated_at();

create table app.event_sources (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references app.events (id) on delete cascade,
  source_id uuid references app.sources (id) on delete set null,
  url text not null check (url ~ '^https?://' and length(url) <= 500),
  url_normalized text not null check (length(url_normalized) <= 500),
  role app.source_role not null,
  first_seen_at timestamptz not null default now(),
  last_checked_at timestamptz,
  last_http_status smallint check (last_http_status between 100 and 599),
  content_hash text check (length(content_hash) <= 128),
  unique (event_id, url_normalized)
);

-- (event_id lookups use the unique (event_id, url_normalized) index)
create index event_sources_source_id_idx on app.event_sources (source_id);

create table app.publications (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references app.events (id) on delete restrict,
  platform app.publication_platform not null,
  target text not null check (length(target) <= 100),
  external_id text check (length(external_id) <= 100),
  content_hash text not null check (content_hash ~ '^[0-9a-f]{64}$'),
  content_version integer not null default 1 check (content_version >= 1),
  body text not null check (length(body) <= 4096),
  image_url text check (image_url ~ '^https://' and length(image_url) <= 500),
  status app.publication_status not null default 'draft',
  sent_at timestamptz,
  edited_at timestamptz,
  deleted_at timestamptz,
  error text check (length(error) <= 2000),
  created_at timestamptz not null default now(),
  unique (platform, target, external_id),
  constraint publications_sent_has_message
    check (status not in ('sent', 'edited') or (external_id is not null and sent_at is not null))
);

create index publications_event_id_idx on app.publications (event_id);

create table app.community_applications (
  id uuid primary key default gen_random_uuid(),
  full_name text not null check (length(btrim(full_name)) between 2 and 120),
  university text check (length(university) <= 160),
  field_of_study text check (length(field_of_study) <= 120),
  year_of_study text
    check (year_of_study in ('prep', '1', '2', '3', '4', '5', '6', 'graduate', 'alumni', 'other')),
  interests text[] not null default '{}'
    check (cardinality(interests) <= 10 and length(array_to_string(interests, ',')) <= 500),
  experience_level text
    check (experience_level in ('none', 'beginner', 'intermediate', 'advanced')),
  looking_for text check (length(looking_for) <= 500),
  preferred_channel text not null check (preferred_channel in ('telegram', 'whatsapp')),
  telegram_username text check (telegram_username ~ '^[A-Za-z0-9_]{5,32}$'),
  phone text check (phone ~ '^\+[1-9][0-9]{7,14}$'),
  message text check (length(message) <= 1000),
  consent_version text not null check (length(consent_version) between 1 and 64),
  consented_at timestamptz not null default now(),
  status app.application_status not null default 'new',
  created_at timestamptz not null default now(),
  -- Contact data is collected only for the chosen channel (data minimisation).
  constraint community_whatsapp_contact
    check (preferred_channel <> 'whatsapp' or (phone is not null and telegram_username is null)),
  constraint community_telegram_contact
    check (preferred_channel <> 'telegram' or (telegram_username is not null and phone is null))
);

create table app.team_applications (
  id uuid primary key default gen_random_uuid(),
  full_name text not null check (length(btrim(full_name)) between 2 and 120),
  affiliation text check (length(affiliation) <= 160),
  areas text[] not null
    check (
      cardinality(areas) between 1 and 7
      and areas <@ array['frontend', 'backend', 'ai_automation', 'design', 'content', 'community', 'research']
    ),
  skills text check (length(skills) <= 500),
  github_url text check (github_url ~ '^https://(www\.)?github\.com/' and length(github_url) <= 200),
  linkedin_url text
    check (linkedin_url ~ '^https://([a-z]{2,3}\.)?(www\.)?linkedin\.com/' and length(linkedin_url) <= 200),
  availability text check (availability in ('1-3h', '4-7h', '8h+')),
  motivation text check (length(motivation) <= 1000),
  consent_version text not null check (length(consent_version) between 1 and 64),
  consented_at timestamptz not null default now(),
  status app.application_status not null default 'new',
  created_at timestamptz not null default now()
);

-- Keep-alive monitoring (D-19). Written only by api.keep_alive().
create table app.heartbeats (
  source text primary key check (source in ('vercel_cron', 'github_actions')),
  last_seen_at timestamptz not null
);

-- ---------------------------------------------------------------------------
-- Row Level Security: enabled everywhere (defense in depth). No policies for
-- anon/authenticated. The backend role gets explicit full-access policies.
-- ---------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array[
    'events', 'sources', 'event_sources', 'publications',
    'community_applications', 'team_applications', 'heartbeats'
  ] loop
    execute format('alter table app.%I enable row level security', t);
    execute format(
      'create policy admin_backend_all on app.%I for all to admin_backend using (true) with check (true)',
      t
    );
    execute format('grant select, insert, update, delete on app.%I to admin_backend', t);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- Reference data needed in every environment.
-- ---------------------------------------------------------------------------
insert into app.sources (name, kind, tier, base_url, retrieval_method, notes) values
  ('Manual entry', 'manual', 4, null, 'manual',
   'Entered by an admin. Not a verification source by itself.'),
  ('Devpost', 'event_platform', 2, 'https://devpost.com', 'manual',
   'Undocumented JSON endpoint exists; see docs/research/CRAWLING_RESEARCH.md.'),
  ('Patika.dev', 'event_platform', 2, 'https://www.patika.dev', 'manual', null);
