-- URL import (V1.2): run log and field evidence. RLS and grants of both tables:
-- 01_privileges.test.sql (every app table).
begin;
create extension if not exists pgtap with schema extensions;

select plan(20);

select has_table('app', 'runs', 'app.runs exists');
select has_table('app', 'event_field_evidence', 'app.event_field_evidence exists');
select has_index(
  'app', 'event_field_evidence', 'event_field_evidence_one_value_per_run',
  'at most one proposed value per field and run'
);
select ok(
  (select relrowsecurity from pg_class where oid = 'app.runs'::regclass)
  and (select relrowsecurity from pg_class where oid = 'app.event_field_evidence'::regclass),
  'RLS is enabled on both tables'
);
select ok(
  not has_table_privilege('anon', 'app.runs', 'SELECT')
  and not has_table_privilege('authenticated', 'app.event_field_evidence', 'SELECT')
  and has_table_privilege('admin_backend', 'app.event_field_evidence', 'INSERT'),
  'only admin_backend can use the tables'
);

insert into app.events (id, slug, title, official_url, official_url_normalized)
values ('00000000-0000-0000-0000-0000000006e1', 'pgtap-import', 'pgTAP import',
        'https://example.com/import', 'example.com/import');
insert into app.event_sources (id, event_id, url, url_normalized, role)
values ('00000000-0000-0000-0000-0000000006a1', '00000000-0000-0000-0000-0000000006e1',
        'https://example.com/import', 'example.com/import', 'official');

-- ---------------------------------------------------------------- runs
select lives_ok(
  $$ insert into app.runs (id, kind, input)
     values ('00000000-0000-0000-0000-0000000006f1', 'url_import',
             '{"url": "https://example.com/import"}') $$,
  'a running import'
);
select is(
  (select status from app.runs where id = '00000000-0000-0000-0000-0000000006f1'),
  'running',
  'a run starts as running'
);
select throws_ok(
  $$ insert into app.runs (kind) values ('crawl') $$,
  '23514', null, 'only known run kinds'
);
select throws_ok(
  $$ update app.runs set status = 'succeeded' where id = '00000000-0000-0000-0000-0000000006f1' $$,
  '23514', null, 'a finished run has finished_at'
);
select throws_ok(
  $$ update app.runs set status = 'failed', finished_at = now()
      where id = '00000000-0000-0000-0000-0000000006f1' $$,
  '23514', null, 'a failed run has an error'
);
select throws_ok(
  $$ insert into app.runs (kind, input) values ('url_import', '[]') $$,
  '23514', null, 'input is an object'
);
select lives_ok(
  $$ update app.runs
        set status = 'succeeded', finished_at = now(),
            event_id = '00000000-0000-0000-0000-0000000006e1', stats = '{"fields": 2}'
      where id = '00000000-0000-0000-0000-0000000006f1' $$,
  'a succeeded run linked to its event'
);

-- ---------------------------------------------------------------- evidence
select lives_ok(
  $$ insert into app.event_field_evidence
       (event_id, field, value_text, source, extracted_by, snippet, run_id, event_source_id)
     values ('00000000-0000-0000-0000-0000000006e1', 'start_date', '2026-11-01', 'jsonld',
             'jsonld', '"startDate": "2026-11-01"', '00000000-0000-0000-0000-0000000006f1',
             '00000000-0000-0000-0000-0000000006a1') $$,
  'a proposed value'
);
select lives_ok(
  $$ insert into app.event_field_evidence (event_id, field, flag, flag_detail, run_id)
     values ('00000000-0000-0000-0000-0000000006e1', 'start_date', 'conflict',
             'The LLM proposed 2026-11-02.', '00000000-0000-0000-0000-0000000006f1') $$,
  'a flag-only row next to the value'
);
select throws_ok(
  $$ insert into app.event_field_evidence (event_id, field, value_text, source, run_id)
     values ('00000000-0000-0000-0000-0000000006e1', 'start_date', '2026-11-03', 'llm',
             '00000000-0000-0000-0000-0000000006f1') $$,
  '23505', null, 'a second value for the same field and run is refused'
);
select throws_ok(
  $$ insert into app.event_field_evidence (event_id, field, value_text)
     values ('00000000-0000-0000-0000-0000000006e1', 'city', 'Elazığ') $$,
  '23514', null, 'a value needs a source'
);
select throws_ok(
  $$ insert into app.event_field_evidence (event_id, field, flag)
     values ('00000000-0000-0000-0000-0000000006e1', 'city', 'invalid') $$,
  '23514', null, 'a flag needs a detail'
);
select throws_ok(
  $$ insert into app.event_field_evidence (event_id, field, value_text, source)
     values ('00000000-0000-0000-0000-0000000006e1', 'City; drop', 'x', 'llm') $$,
  '23514', null, 'field is a column-like name'
);

delete from app.events where id = '00000000-0000-0000-0000-0000000006e1';
select is(
  (select count(*)::int from app.event_field_evidence
    where event_id = '00000000-0000-0000-0000-0000000006e1'),
  0,
  'evidence is deleted with its event'
);
select is(
  (select event_id from app.runs where id = '00000000-0000-0000-0000-0000000006f1'),
  null,
  'the run outlives its event'
);

select * from finish();
rollback;
