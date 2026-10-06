-- Channel publishing (V1.1a): one draft/live post per event, message type of sent posts,
-- admin bot channel offers. RLS and grants of app.publications: 01_privileges.test.sql.
begin;
create extension if not exists pgtap with schema extensions;

select plan(9);

select has_column('app', 'publications', 'message_type', 'publications record the message type');
select has_index(
  'app', 'publications', 'publications_one_live_per_event',
  'at most one draft or live post per event'
);

insert into app.events (id, slug, title, official_url, official_url_normalized)
values ('00000000-0000-0000-0000-0000000005e1', 'pgtap-channel', 'pgTAP channel',
        'https://example.com', 'example.com');

insert into app.publications (event_id, platform, target, content_hash, body, status)
values ('00000000-0000-0000-0000-0000000005e1', 'telegram', '@c', repeat('a', 64), 'b', 'draft');

select throws_ok(
  $$ insert into app.publications (event_id, platform, target, content_hash, body, status)
     values ('00000000-0000-0000-0000-0000000005e1', 'telegram', '@c', repeat('a', 64), 'b',
             'draft') $$,
  '23505', null, 'a second draft for the same event is refused'
);
select throws_ok(
  $$ update app.publications set status = 'sent', external_id = '5', sent_at = now()
      where event_id = '00000000-0000-0000-0000-0000000005e1' $$,
  '23514', null, 'a sent post needs a message type'
);
select lives_ok(
  $$ update app.publications
        set status = 'sent', external_id = '5', sent_at = now(), message_type = 'photo'
      where event_id = '00000000-0000-0000-0000-0000000005e1' $$,
  'a sent photo post'
);
select throws_ok(
  $$ insert into app.publications (event_id, platform, target, content_hash, body, status)
     values ('00000000-0000-0000-0000-0000000005e1', 'telegram', '@c', repeat('a', 64), 'b',
             'draft') $$,
  '23505', null, 'no new draft while a post is live'
);
update app.publications set status = 'deleted', deleted_at = now()
 where event_id = '00000000-0000-0000-0000-0000000005e1';
select lives_ok(
  $$ insert into app.publications (event_id, platform, target, content_hash, body, status)
     values ('00000000-0000-0000-0000-0000000005e1', 'telegram', '@c', repeat('a', 64), 'b',
             'draft') $$,
  'a deleted post frees the slot'
);

select lives_ok(
  $$ insert into app.bot_notifications
       (entity_type, entity_id, kind, state_token, chat_id, message_id, sent_at,
        resolved_at, resolution, confirm_action, confirm_at)
     values ('event', '00000000-0000-0000-0000-0000000005e1', 'channel_post', '0123abcd',
             1111, 77, now(), now(), 'posted', 'channel_post', now()) $$,
  'channel offers use the new kind, resolution and confirm action'
);
select throws_ok(
  $$ insert into app.bot_notifications (entity_type, entity_id, kind, state_token, chat_id)
     values ('community_application', '00000000-0000-0000-0000-0000000005c1',
             'channel_update', '0123abcd', 1111) $$,
  '23514', null, 'channel offers are about events only'
);

select * from finish();
rollback;
