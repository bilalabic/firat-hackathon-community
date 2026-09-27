-- Event visibility and event constraints (MVP criteria 5, 12).
begin;
create extension if not exists pgtap with schema extensions;

select plan(10);

insert into app.events (slug, title, official_url, official_url_normalized, start_date, status, published_at)
values
  ('t-draft', 'Test draft', 'https://t.dev/1', 't.dev/1', '2030-01-01', 'draft', null),
  ('t-review', 'Test review', 'https://t.dev/2', 't.dev/2', '2030-01-01', 'in_review', null),
  ('t-approved', 'Test approved', 'https://t.dev/3', 't.dev/3', '2030-01-01', 'approved', null),
  ('t-archived', 'Test archived', 'https://t.dev/4', 't.dev/4', '2030-01-01', 'archived', null),
  ('t-rejected', 'Test rejected', 'https://t.dev/5', 't.dev/5', '2030-01-01', 'rejected', null),
  ('t-published', 'Test published', 'https://t.dev/6', 't.dev/6', '2030-01-01', 'published', now());

insert into app.events
  (slug, title, official_url, official_url_normalized, start_date, status, published_at, duplicate_of)
select 't-dup', 'Test duplicate', 'https://t.dev/7', 't.dev/7', '2030-01-01', 'published', now(), id
from app.events where slug = 't-published';

set local role anon;
select results_eq(
  $$ select slug from api.events_public where slug like 't-%' order by slug $$,
  array['t-published'],
  'anon sees only the published, non-duplicate test event'
);
select ok(
  (select count(*) from api.events_public where slug not like 't-%') >= 1,
  'seeded legacy events are visible'
);
reset role;

-- Constraints that protect what the public site shows.
select throws_ok(
  $$ insert into app.events (slug, title, official_url, official_url_normalized, status, published_at)
     values ('t-no-start', 'No start', 'https://t.dev/8', 't.dev/8', 'published', now()) $$,
  '23514', null, 'a published event requires start_date'
);
select throws_ok(
  $$ insert into app.events (slug, title, official_url, official_url_normalized, start_date, status)
     values ('t-no-pub-at', 'No published_at', 'https://t.dev/9', 't.dev/9', '2030-01-01', 'published') $$,
  '23514', null, 'a published event requires published_at'
);
select throws_ok(
  $$ insert into app.events (slug, title, official_url, official_url_normalized, start_date, end_date)
     values ('t-bad-dates', 'Bad dates', 'https://t.dev/10', 't.dev/10', '2030-01-05', '2030-01-01') $$,
  '23514', null, 'end_date cannot be before start_date'
);
select throws_ok(
  $$ insert into app.events (slug, title, official_url, official_url_normalized)
     values ('Bad Slug', 'Bad slug', 'https://t.dev/11', 't.dev/11') $$,
  '23514', null, 'slug must be lower-case kebab-case'
);
select throws_ok(
  $$ insert into app.events (slug, title, official_url, official_url_normalized, team_min, team_max)
     values ('t-team', 'Team order', 'https://t.dev/12', 't.dev/12', 4, 2) $$,
  '23514', null, 'team_min cannot exceed team_max'
);
select throws_ok(
  $$ insert into app.events (slug, title, official_url, official_url_normalized, prize_pool)
     values ('t-prize', 'Prize', 'https://t.dev/13', 't.dev/13', 1000) $$,
  '23514', null, 'prize_pool requires currency'
);
select throws_ok(
  $$ insert into app.events (slug, title, official_url, official_url_normalized)
     values ('t-js', 'JS url', 'javascript:alert(1)', 'x') $$,
  '23514', null, 'official_url must be http(s)'
);
select throws_ok(
  $$ insert into app.publications (event_id, platform, target, content_hash, body, status)
     select id, 'telegram', '@ch', repeat('a', 64), 'x', 'sent' from app.events where slug = 't-published' $$,
  '23514', null, 'a sent publication requires external_id and sent_at'
);

select * from finish();
rollback;
