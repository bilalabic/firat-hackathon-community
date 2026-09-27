-- Privilege and exposure rules (docs/architecture/DATA_MODEL.md §4, MVP criterion 5).
-- Checks use the catalog (has_*_privilege) rather than information_schema, which hides
-- grants made by roles other than the current one.
begin;
create extension if not exists pgtap with schema extensions;

select plan(24);

-- ---------------------------------------------------------------- app schema
select is(
  (select count(*)::int from pg_class
    where relnamespace = 'app'::regnamespace and relkind = 'r' and not relrowsecurity),
  0,
  'RLS is enabled on every app table'
);

select is(
  (select count(*)::int from pg_class c
    where c.relnamespace = 'app'::regnamespace and c.relkind = 'r'
      and not exists (
        select 1 from pg_policies p
        where p.schemaname = 'app' and p.tablename = c.relname and 'admin_backend' = any (p.roles)
      )),
  0,
  'every app table has an admin_backend policy'
);

select is(
  (select count(*)::int from pg_class c
    where c.relnamespace = 'app'::regnamespace and c.relkind = 'r'
      and not (has_table_privilege('admin_backend', c.oid, 'SELECT')
           and has_table_privilege('admin_backend', c.oid, 'INSERT')
           and has_table_privilege('admin_backend', c.oid, 'UPDATE')
           and has_table_privilege('admin_backend', c.oid, 'DELETE'))),
  0,
  'admin_backend has CRUD on every app table'
);

select is(
  (select count(*)::int from pg_class c
    where c.relnamespace = 'app'::regnamespace and c.relkind = 'r'
      and has_table_privilege('admin_backend', c.oid, 'TRUNCATE')),
  0,
  'admin_backend cannot TRUNCATE'
);

select is(
  (select count(*)::int
     from pg_class c
     cross join unnest(array['anon', 'authenticated', 'service_role']) as r(role)
    where c.relnamespace in ('app'::regnamespace, 'public'::regnamespace)
      and c.relkind in ('r', 'v', 'm', 'S')
      and has_table_privilege(r.role, c.oid,
            'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')),
  0,
  'API roles have no privilege on any app or public relation'
);

select is(
  (select count(*)::int
     from pg_proc p
     cross join unnest(array['anon', 'authenticated', 'service_role']) as r(role)
    where p.pronamespace = 'app'::regnamespace
      and has_function_privilege(r.role, p.oid, 'EXECUTE')),
  0,
  'API roles cannot execute any app function'
);

select ok(not has_schema_privilege('anon', 'app', 'USAGE'), 'anon has no usage on schema app');
select ok(not has_schema_privilege('authenticated', 'app', 'USAGE'), 'authenticated has no usage on schema app');
select ok(not has_schema_privilege('service_role', 'app', 'USAGE'), 'service_role has no usage on schema app');

-- ---------------------------------------------------------------- api surface
select ok(has_schema_privilege('anon', 'api', 'USAGE'), 'anon has usage on schema api');
select ok(not has_schema_privilege('authenticated', 'api', 'USAGE'), 'authenticated has no usage on schema api');
select ok(not has_schema_privilege('service_role', 'api', 'USAGE'), 'service_role has no usage on schema api');

select tables_are('api', array[]::name[], 'api has no tables');
select views_are('api', array['events_public'], 'api has exactly one view');
select functions_are(
  'api',
  array['keep_alive', 'submit_community_application', 'submit_team_application'],
  'api has exactly the three expected functions'
);
select table_privs_are('api', 'events_public', 'anon', array['SELECT'], 'anon can only SELECT events_public');

select is(
  (select count(*)::int from pg_proc
    where pronamespace = 'api'::regnamespace
      and has_function_privilege('anon', oid, 'EXECUTE')),
  3,
  'anon can execute exactly the three api functions'
);

select is(
  (select count(*)::int from pg_proc
    where pronamespace = 'api'::regnamespace
      and (prosecdef is not true or not ('search_path=""' = any (coalesce(proconfig, '{}'))))),
  0,
  'every api function is security definer with an empty search_path'
);

select hasnt_column('api', 'events_public', 'internal_notes', 'internal_notes is not exposed');
select hasnt_column('api', 'events_public', 'status', 'status is not exposed');
select hasnt_column('api', 'events_public', 'duplicate_of', 'duplicate_of is not exposed');

-- ---------------------------------------------------------------- future objects
-- Objects created later must not become callable/readable by anon by default.
create function api.zz_future_probe() returns int language sql as 'select 1';
create table api.zz_future_table (id int);
select ok(
  not has_function_privilege('anon', 'api.zz_future_probe()', 'EXECUTE')
  and not has_table_privilege('anon', 'api.zz_future_table', 'SELECT'),
  'new api functions and tables are not exposed to anon by default'
);

-- ---------------------------------------------------------------- behavior as anon
set local role anon;
select throws_ok('select * from app.community_applications', '42501', null, 'anon cannot read applications');
select throws_ok('select * from app.events', '42501', null, 'anon cannot read app.events directly');
reset role;

select * from finish();
rollback;
