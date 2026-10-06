-- Admin bot tables (V1.1b): outbox idempotency, audit constraints, no API-role access.
-- RLS, policies and grants for these tables are covered by 01_privileges.test.sql.
begin;
create extension if not exists pgtap with schema extensions;

select plan(14);

select has_table('app', 'bot_state', 'app.bot_state exists');
select has_table('app', 'bot_notifications', 'app.bot_notifications exists');
select has_table('app', 'bot_pending_replies', 'app.bot_pending_replies exists');
select has_table('app', 'admin_actions', 'app.admin_actions exists');

-- ---------------------------------------------------------------- outbox idempotency
insert into app.bot_notifications (id, entity_type, entity_id, kind, state_token, chat_id)
values ('00000000-0000-0000-0000-0000000000a1', 'event',
        '00000000-0000-0000-0000-0000000000e1', 'review', '0123abcd', 1111);

select throws_ok(
  $$ insert into app.bot_notifications (entity_type, entity_id, kind, state_token, chat_id)
     values ('event', '00000000-0000-0000-0000-0000000000e1', 'review', '0123abcd', 1111) $$,
  '23505', null, 'the same entity state cannot be claimed twice for one chat'
);
select lives_ok(
  $$ insert into app.bot_notifications (entity_type, entity_id, kind, state_token, chat_id)
     values ('event', '00000000-0000-0000-0000-0000000000e1', 'review', '0123abcd', 2222) $$,
  'another admin chat gets its own slot'
);

update app.bot_notifications
   set message_id = 10, sent_at = now(), resolved_at = now(), resolution = 'expired'
 where id = '00000000-0000-0000-0000-0000000000a1';
select lives_ok(
  $$ insert into app.bot_notifications (entity_type, entity_id, kind, state_token, chat_id)
     values ('event', '00000000-0000-0000-0000-0000000000e1', 'review', '0123abcd', 1111) $$,
  'an expired message frees the slot for a fresh one'
);

select throws_ok(
  $$ update app.bot_notifications set message_id = 11 where chat_id = 2222 $$,
  '23514', null, 'message_id and sent_at are set together'
);
select throws_ok(
  $$ insert into app.bot_notifications (entity_type, entity_id, kind, state_token, chat_id)
     values ('community_application', '00000000-0000-0000-0000-0000000000c1', 'review',
             '0123abcd', 1111) $$,
  '23514', null, 'kind must match the entity type'
);

select throws_ok(
  $$ update app.bot_notifications set confirm_action = 'publish' where chat_id = 2222 $$,
  '23514', null, 'confirm_action and confirm_at are set together'
);

-- ---------------------------------------------------------------- applications
select has_column('app', 'community_applications', 'updated_at', 'community applications have updated_at');
select has_trigger(
  'app', 'team_applications', 'team_applications_set_updated_at',
  'team applications maintain updated_at'
);

-- ---------------------------------------------------------------- audit
select throws_ok(
  $$ insert into app.admin_actions (actor, action, entity_type, entity_id)
     values ('telegram:@bilal', 'approve', 'event', '00000000-0000-0000-0000-0000000000e1') $$,
  '23514', null, 'audit actor must be admin_ui or telegram:<numeric id>'
);

-- ---------------------------------------------------------------- API roles
set local role anon;
select throws_ok('select * from app.admin_actions', '42501', null, 'anon cannot read the audit');
reset role;

select * from finish();
rollback;
