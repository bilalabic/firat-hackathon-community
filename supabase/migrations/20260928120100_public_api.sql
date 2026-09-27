-- Public Data API surface. This is the ONLY schema exposed by PostgREST.
-- anon (publishable key) can: read published events, submit two forms, send a keep-alive.
-- Nothing else. The exact surface is pinned by supabase/tests/database/01_privileges.test.sql.
-- Design: docs/architecture/DATA_MODEL.md §4

create schema api;
revoke all on schema api from public;
grant usage on schema api to anon;

-- ---------------------------------------------------------------------------
-- Published events, public columns only.
-- Intentionally NOT security_invoker: the view (owned by postgres) is the filter,
-- and anon has no privilege on app.events itself.
-- ---------------------------------------------------------------------------
create view api.events_public with (security_barrier = true) as
select
  e.id,
  e.slug,
  e.title,
  e.organizer,
  e.summary,
  e.description,
  e.categories,
  e.technologies,
  e.format,
  e.city,
  e.country,
  e.venue,
  e.start_date,
  e.end_date,
  e.application_deadline,
  e.timezone,
  e.eligibility,
  e.team_min,
  e.team_max,
  e.prize_pool,
  e.currency,
  e.is_free,
  e.official_url,
  e.application_url,
  e.poster_url,
  e.banner_url,
  e.organizer_logo_url,
  e.verification_status,
  e.published_at,
  e.updated_at
from app.events e
where e.status = 'published'
  and e.duplicate_of is null;

revoke all on api.events_public from public, anon, authenticated, service_role;
grant select on api.events_public to anon;

-- ---------------------------------------------------------------------------
-- Payload helpers (private; not exposed, not executable by API roles).
-- ---------------------------------------------------------------------------

-- Raises unless every value is a JSON string or null, except the listed array keys.
create function app.assert_flat_payload(payload jsonb, array_keys text[]) returns void
language plpgsql
immutable
set search_path = ''
as $$
begin
  if jsonb_typeof(payload) is distinct from 'object' then
    raise exception 'invalid application' using errcode = '22023';
  end if;
  if exists (
    select 1
    from jsonb_each(payload) as kv
    where not (kv.key = any (array_keys))
      and jsonb_typeof(kv.value) not in ('string', 'null')
  ) then
    raise exception 'invalid application' using errcode = '22023';
  end if;
end;
$$;

-- Distinct, trimmed, non-empty strings of a JSON array; null if the value is not an array
-- of strings.
create function app.text_array(value jsonb) returns text[]
language sql
immutable
set search_path = ''
as $$
  select case
    when jsonb_typeof(value) is distinct from 'array' then null
    when exists (select 1 from jsonb_array_elements(value) as el where jsonb_typeof(el) <> 'string')
      then null
    else array(
      select distinct btrim(v)
      from jsonb_array_elements_text(value) as v
      where btrim(v) <> ''
      order by 1
    )
  end;
$$;

revoke all on function app.assert_flat_payload(jsonb, text[]) from public;
revoke all on function app.text_array(jsonb) from public;

-- ---------------------------------------------------------------------------
-- Form submissions. Return nothing, so no data can be read back.
-- Constraint errors are mapped to one generic error to avoid leaking schema details.
-- ---------------------------------------------------------------------------
create function api.submit_community_application(payload jsonb) returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_channel text;
  v_interests text[];
begin
  perform app.assert_flat_payload(payload, array['interests']);
  v_channel := nullif(btrim(payload ->> 'preferred_channel'), '');
  v_interests := case
    when coalesce(payload -> 'interests', 'null'::jsonb) = 'null'::jsonb then '{}'
    else app.text_array(payload -> 'interests')
  end;
  if v_interests is null then
    raise exception 'invalid application' using errcode = '22023';
  end if;

  insert into app.community_applications (
    full_name, university, field_of_study, year_of_study, interests, experience_level,
    looking_for, preferred_channel, telegram_username, phone, message, consent_version
  ) values (
    nullif(btrim(payload ->> 'full_name'), ''),
    nullif(btrim(payload ->> 'university'), ''),
    nullif(btrim(payload ->> 'field_of_study'), ''),
    nullif(btrim(payload ->> 'year_of_study'), ''),
    v_interests,
    nullif(btrim(payload ->> 'experience_level'), ''),
    nullif(btrim(payload ->> 'looking_for'), ''),
    v_channel,
    -- Contact data is stored only for the chosen channel (data minimisation).
    case when v_channel = 'telegram'
      then nullif(ltrim(btrim(payload ->> 'telegram_username'), '@'), '') end,
    case when v_channel = 'whatsapp' then nullif(btrim(payload ->> 'phone'), '') end,
    nullif(btrim(payload ->> 'message'), ''),
    nullif(btrim(payload ->> 'consent_version'), '')
  );
exception
  when check_violation or not_null_violation or string_data_right_truncation
    or invalid_text_representation then
    raise exception 'invalid application' using errcode = '22023';
end;
$$;

create function api.submit_team_application(payload jsonb) returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform app.assert_flat_payload(payload, array['areas']);

  insert into app.team_applications (
    full_name, affiliation, areas, skills, github_url, linkedin_url, availability,
    motivation, consent_version
  ) values (
    nullif(btrim(payload ->> 'full_name'), ''),
    nullif(btrim(payload ->> 'affiliation'), ''),
    app.text_array(payload -> 'areas'),
    nullif(btrim(payload ->> 'skills'), ''),
    nullif(btrim(payload ->> 'github_url'), ''),
    nullif(btrim(payload ->> 'linkedin_url'), ''),
    nullif(btrim(payload ->> 'availability'), ''),
    nullif(btrim(payload ->> 'motivation'), ''),
    nullif(btrim(payload ->> 'consent_version'), '')
  );
exception
  when check_violation or not_null_violation or string_data_right_truncation
    or invalid_text_representation then
    raise exception 'invalid application' using errcode = '22023';
end;
$$;

-- ---------------------------------------------------------------------------
-- Keep-alive (D-19): records a heartbeat and performs a real read.
-- Idempotent: it only sets a timestamp.
-- ---------------------------------------------------------------------------
create function api.keep_alive(source text) returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_count bigint;
begin
  if source is null or source not in ('vercel_cron', 'github_actions') then
    raise exception 'invalid source' using errcode = '22023';
  end if;

  insert into app.heartbeats as h (source, last_seen_at)
  values (keep_alive.source, now())
  on conflict on constraint heartbeats_pkey do update set last_seen_at = excluded.last_seen_at;

  select count(*) into v_count from app.events where status = 'published';
  return v_count;
end;
$$;

revoke all on function api.submit_community_application(jsonb) from public, anon, authenticated, service_role;
revoke all on function api.submit_team_application(jsonb) from public, anon, authenticated, service_role;
revoke all on function api.keep_alive(text) from public, anon, authenticated, service_role;
grant execute on function api.submit_community_application(jsonb) to anon;
grant execute on function api.submit_team_application(jsonb) to anon;
grant execute on function api.keep_alive(text) to anon;
