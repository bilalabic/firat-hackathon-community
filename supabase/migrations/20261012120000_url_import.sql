-- V1.2: URL import and extraction (docs/planning/V1_2_URL_IMPORT.md, DATA_MODEL §5).
-- Written only by the local admin API (admin_backend). No personal data: the input is a
-- public event URL, snippets are short quotes from the event page.

-- ---------------------------------------------------------------------------
-- Pipeline run log. A run is inserted as 'running' (committed) before the slow work, so
-- a crashed import stays visible; it ends as 'succeeded' or 'failed'.
-- ---------------------------------------------------------------------------
create table app.runs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('url_import')),
  status text not null default 'running' check (status in ('running', 'succeeded', 'failed')),
  -- {"url": "..."}
  input jsonb not null default '{}'::jsonb
    check (jsonb_typeof(input) = 'object' and length(input::text) <= 2000),
  -- Durations, field and flag counts, extracted_by, the og:image suggestion.
  stats jsonb not null default '{}'::jsonb
    check (jsonb_typeof(stats) = 'object' and length(stats::text) <= 10000),
  error text check (length(error) <= 2000),
  -- The created (or, for a duplicate found after redirects, the existing) event.
  event_id uuid references app.events (id) on delete set null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  constraint runs_finished_when_done check ((status = 'running') = (finished_at is null)),
  constraint runs_failed_has_error check (status <> 'failed' or error is not null),
  constraint runs_finished_after_start check (finished_at is null or finished_at >= started_at)
);

create index runs_started_at_idx on app.runs (started_at desc, id);
create index runs_event_id_idx on app.runs (event_id) where event_id is not null;

-- ---------------------------------------------------------------------------
-- Field-level provenance. One row per proposed value and one row per flag (a field can
-- have a value and several flags, e.g. a kept JSON-LD value and an LLM conflict). History
-- is kept: a new import adds rows; the review page shows the latest run.
-- ---------------------------------------------------------------------------
create table app.event_field_evidence (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references app.events (id) on delete cascade,
  -- An app.events column name. Not an enum: the extractable set grows (description,
  -- categories) without a migration; the API only writes its known fields.
  field text not null check (field ~ '^[a-z_]{1,40}$'),
  -- The proposed value as text (ISO date, decimal, true/false); null on a flag-only row.
  value_text text check (length(value_text) <= 5000),
  -- Where the value came from; null on a flag-only row.
  source text check (source in ('jsonld', 'meta', 'llm', 'manual')),
  -- 'llm:<model>' for LLM values, else the structured source.
  extracted_by text check (length(extracted_by) <= 100),
  snippet text check (length(snippet) <= 500),
  flag text check (flag in ('unsupported', 'conflict', 'rule_violation', 'invalid')),
  flag_detail text check (length(flag_detail) <= 500),
  run_id uuid references app.runs (id) on delete set null,
  event_source_id uuid references app.event_sources (id) on delete set null,
  extracted_at timestamptz not null default now(),
  constraint event_field_evidence_value_or_flag check (value_text is not null or flag is not null),
  constraint event_field_evidence_value_has_source check ((value_text is null) = (source is null)),
  constraint event_field_evidence_flag_has_detail check ((flag is null) = (flag_detail is null))
);

-- Latest rows per event.
create index event_field_evidence_event_idx on app.event_field_evidence (event_id, extracted_at desc);
-- At most one proposed value per field and run.
create unique index event_field_evidence_one_value_per_run
  on app.event_field_evidence (run_id, field)
  where value_text is not null;
create index event_field_evidence_run_idx on app.event_field_evidence (run_id);
create index event_field_evidence_event_source_idx
  on app.event_field_evidence (event_source_id) where event_source_id is not null;

-- ---------------------------------------------------------------------------
-- Same access model as every app table (01_privileges.test.sql enforces it).
-- ---------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array['runs', 'event_field_evidence']
  loop
    execute format('alter table app.%I enable row level security', t);
    execute format(
      'create policy admin_backend_all on app.%I for all to admin_backend using (true) with check (true)',
      t
    );
    execute format('grant select, insert, update, delete on app.%I to admin_backend', t);
  end loop;
end;
$$;
