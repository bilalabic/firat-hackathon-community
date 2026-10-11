-- V1.1a: Telegram channel publishing (D-12, D-14, D-17). Written only by the local admin
-- API (admin_backend). `app.publications` exists since the core schema; this adds what the
-- publishing flow needs.

-- ---------------------------------------------------------------------------
-- What kind of Telegram message a post is: a photo with a caption (the event card), or a
-- text message with a link preview (fallback when Telegram could not fetch the card).
-- Edits depend on it (editMessageCaption only works on media messages).
-- ---------------------------------------------------------------------------
alter table app.publications
  add column message_type text check (message_type in ('photo', 'text'));

alter table app.publications
  add constraint publications_sent_has_type
    check (status not in ('sent', 'edited') or message_type is not null);

-- A failed send whose outcome is unknown (timeout, unreadable answer, 5xx): the message may
-- exist in the channel. It blocks a new send until an operator has checked the channel and
-- resolved it (`uncertain` back to false).
alter table app.publications
  add column uncertain boolean not null default false;

alter table app.publications
  add constraint publications_uncertain_is_failed
    check (not uncertain or status = 'failed');

-- An edit in progress: claimed before the Bot API call and cleared afterwards, so two
-- concurrent updates cannot both edit the message.
alter table app.publications
  add column updating_since timestamptz;

alter table app.publications
  add constraint publications_updating_is_live
    check (updating_since is null or status in ('sent', 'edited'));

-- A post is claimed as 'draft' before the Bot API call and becomes 'sent' or 'failed'
-- afterwards. At most one draft, uncertain or live post per event and platform: a
-- concurrent second send (admin UI and admin bot) fails on this index instead of posting
-- twice.
create unique index publications_one_live_per_event
  on app.publications (event_id, platform)
  where status in ('draft', 'sent', 'edited') or uncertain;

-- ---------------------------------------------------------------------------
-- Admin bot (V1.1b): "Post to channel" / "Update channel post" offers for published events.
-- ---------------------------------------------------------------------------
alter table app.bot_notifications drop constraint bot_notifications_kind_check;
alter table app.bot_notifications
  add constraint bot_notifications_kind_check
    check (kind in ('review', 'publish', 'application', 'channel_post', 'channel_update'));

alter table app.bot_notifications drop constraint bot_notifications_resolution_check;
alter table app.bot_notifications
  add constraint bot_notifications_resolution_check
    check (
      resolution in (
        'approved', 'changes_requested', 'rejected', 'published', 'later',
        'contacted', 'accepted', 'declined', 'spam', 'superseded', 'expired',
        'posted', 'updated'
      )
    );

alter table app.bot_notifications drop constraint bot_notifications_confirm_action_check;
alter table app.bot_notifications
  add constraint bot_notifications_confirm_action_check
    check (confirm_action in ('publish', 'reject', 'channel_post', 'channel_update'));
