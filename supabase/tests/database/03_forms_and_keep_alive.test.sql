-- Public form functions and keep-alive (MVP criteria 5, 15, 21).
begin;
create extension if not exists pgtap with schema extensions;

select plan(20);

set local role anon;

-- ---------------------------------------------------------------- community
select lives_ok(
  $$ select api.submit_community_application('{
       "full_name": "Ayşe Yılmaz", "university": "Fırat Üniversitesi",
       "year_of_study": "3", "interests": ["ai", "web", "ai", " "], "experience_level": "beginner",
       "preferred_channel": "telegram", "telegram_username": "@ayse_dev", "phone": "+905551112233",
       "consent_version": "2026-10-community-v1"
     }'::jsonb) $$,
  'valid Telegram community application is accepted'
);
select lives_ok(
  $$ select api.submit_community_application('{
       "full_name": "Mehmet Kaya", "preferred_channel": "whatsapp", "telegram_username": "mehmet_k",
       "phone": "+905551112233", "consent_version": "2026-10-community-v1"
     }'::jsonb) $$,
  'valid WhatsApp community application is accepted'
);
select throws_ok(
  $$ select api.submit_community_application('{
       "full_name": "No Phone", "preferred_channel": "whatsapp", "consent_version": "v1"
     }'::jsonb) $$,
  '22023', 'invalid application', 'WhatsApp without phone is rejected'
);
select throws_ok(
  $$ select api.submit_community_application('{
       "full_name": "No Username", "preferred_channel": "telegram", "consent_version": "v1"
     }'::jsonb) $$,
  '22023', 'invalid application', 'Telegram without username is rejected'
);
select throws_ok(
  $$ select api.submit_community_application('{
       "full_name": "No Consent", "preferred_channel": "telegram", "telegram_username": "abcde"
     }'::jsonb) $$,
  '22023', 'invalid application', 'missing consent is rejected'
);
select throws_ok(
  $$ select api.submit_community_application('{
       "full_name": "Bad Phone", "preferred_channel": "whatsapp", "phone": "0555 111 22 33",
       "consent_version": "v1"
     }'::jsonb) $$,
  '22023', 'invalid application', 'non-E.164 phone is rejected'
);
select throws_ok(
  $$ select api.submit_community_application('{
       "full_name": {"a": 1}, "preferred_channel": "telegram", "telegram_username": "abcde",
       "consent_version": "v1"
     }'::jsonb) $$,
  '22023', 'invalid application', 'non-string scalar fields are rejected'
);
select throws_ok(
  $$ select api.submit_community_application('{
       "full_name": "Bad Interests", "preferred_channel": "telegram", "telegram_username": "abcde",
       "interests": [1, 2], "consent_version": "v1"
     }'::jsonb) $$,
  '22023', 'invalid application', 'non-string interests are rejected'
);
select throws_ok(
  $$ select api.submit_community_application('[]'::jsonb) $$,
  '22023', 'invalid application', 'non-object payload is rejected'
);

-- ---------------------------------------------------------------- team
select lives_ok(
  $$ select api.submit_team_application('{
       "full_name": "Zeynep Ak", "areas": ["frontend", "design", "design"],
       "github_url": "https://github.com/zeynep", "availability": "4-7h",
       "consent_version": "2026-10-team-v1"
     }'::jsonb) $$,
  'valid team application is accepted'
);
select throws_ok(
  $$ select api.submit_team_application('{"full_name": "Bad Area", "areas": ["hacking"], "consent_version": "v1"}'::jsonb) $$,
  '22023', 'invalid application', 'unknown team area is rejected'
);
select throws_ok(
  $$ select api.submit_team_application('{"full_name": "No Areas", "consent_version": "v1"}'::jsonb) $$,
  '22023', 'invalid application', 'team application without areas is rejected'
);
select throws_ok(
  $$ select api.submit_team_application('{
       "full_name": "Bad Github", "areas": ["backend"], "github_url": "https://evil.dev/x",
       "consent_version": "v1"
     }'::jsonb) $$,
  '22023', 'invalid application', 'non-GitHub github_url is rejected'
);

-- ---------------------------------------------------------------- keep-alive
select ok(api.keep_alive('vercel_cron') >= 1, 'keep_alive returns the published event count');
select lives_ok($$ select api.keep_alive('vercel_cron') $$, 'keep_alive is repeatable (idempotent upsert)');
select lives_ok($$ select api.keep_alive('github_actions') $$, 'keep_alive accepts github_actions');
select throws_ok(
  $$ select api.keep_alive('someone_else') $$, '22023', 'invalid source', 'keep_alive rejects unknown sources'
);

reset role;

-- ---------------------------------------------------------------- stored data
select results_eq(
  $$ select telegram_username, phone, interests from app.community_applications where full_name = 'Ayşe Yılmaz' $$,
  $$ values ('ayse_dev'::text, null::text, array['ai', 'web']::text[]) $$,
  'Telegram: @ stripped, phone dropped, interests trimmed and de-duplicated'
);
select results_eq(
  $$ select telegram_username, phone from app.community_applications where full_name = 'Mehmet Kaya' $$,
  $$ values (null::text, '+905551112233'::text) $$,
  'WhatsApp: Telegram username dropped, phone kept'
);
select is(
  (select count(*)::int from app.heartbeats),
  2,
  'one heartbeat row per source'
);

select * from finish();
rollback;
