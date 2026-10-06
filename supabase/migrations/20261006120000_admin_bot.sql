-- V1.1b: admin decisions via Telegram (D-21, docs/planning/V1_1B_TELEGRAM_ADMIN.md).
-- Written only by the local admin API (admin_backend). No personal data is stored here:
-- entities are referenced by id, and reasons stay in app.events.internal_notes.

-- ---------------------------------------------------------------------------
-- Applications get `updated_at` (like events), so the bot's state token changes on every
-- status change, including new -> contacted -> new (the application is notified again).
-- ---------------------------------------------------------------------------
alter table app.community_applications add column updated_at timestamptz not null default now();
alter table app.team_applications add column updated_at timestamptz not null default now();

create trigger community_applications_set_updated_at
  before update on app.community_applications
  for each row execute function app.set_updated_at();
create trigger team_applications_set_updated_at
  before update on app.team_applications
  for each row execute function app.set_updated_at();

-- ---------------------------------------------------------------------------
-- Small key/value store (e.g. the getUpdates offset per bot).
-- ---------------------------------------------------------------------------
create table app.bot_state (
  key text primary key check (key ~ '^[a-z0-9_.:-]{1,100}$'),
  value text not null check (length(value) <= 1000),
  updated_at timestamptz not null default now()
);

create trigger bot_state_set_updated_at
  before update on app.bot_state
  for each row execute function app.set_updated_at();

-- ---------------------------------------------------------------------------
-- One row per Telegram message the admin bot sent (or is sending) to one admin chat.
-- A row is "claimed" (message_id null) before sendMessage and filled in afterwards.
-- ---------------------------------------------------------------------------
create table app.bot_notifications (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null
    check (entity_type in ('event', 'community_application', 'team_application')),
  entity_id uuid not null,
  kind text not null check (kind in ('review', 'publish', 'application')),
  -- Short hash of the entity's `updated_at` when the buttons were made. A press with
  -- another token is stale.
  state_token text not null check (state_token ~ '^[0-9a-f]{8}$'),
  chat_id bigint not null,
  message_id bigint check (message_id > 0),
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  resolved_at timestamptz,
  resolution text check (
    resolution in (
      'approved', 'changes_requested', 'rejected', 'published', 'later',
      'contacted', 'accepted', 'declined', 'spam', 'superseded', 'expired'
    )
  ),
  -- Two-step confirmation, enforced by the server: the first Publish/Reject press records
  -- the stage; the matching Confirm press is accepted only while it is recent.
  confirm_action text check (confirm_action in ('publish', 'reject')),
  confirm_at timestamptz,
  constraint bot_notifications_sent_has_message
    check ((message_id is null) = (sent_at is null)),
  constraint bot_notifications_confirm_together
    check ((confirm_action is null) = (confirm_at is null)),
  constraint bot_notifications_resolved_together
    check ((resolved_at is null) = (resolution is null)),
  constraint bot_notifications_kind_matches_entity
    check ((kind = 'application') = (entity_type <> 'event'))
);

-- Outbox idempotency: at most one live message per entity state and admin chat, across
-- restarts and concurrent scans (INSERT ... ON CONFLICT DO NOTHING claims the slot).
-- An 'expired' message no longer counts, so a fresh one can be sent for the same state.
create unique index bot_notifications_identity_key
  on app.bot_notifications (entity_type, entity_id, kind, state_token, chat_id)
  where resolution is null or resolution <> 'expired';

create unique index bot_notifications_message_key
  on app.bot_notifications (chat_id, message_id)
  where message_id is not null;

create index bot_notifications_unresolved_idx
  on app.bot_notifications (entity_type, entity_id, kind)
  where resolved_at is null;

-- ---------------------------------------------------------------------------
-- Reason prompts (force_reply) waiting for the admin's reply.
-- ---------------------------------------------------------------------------
create table app.bot_pending_replies (
  id uuid primary key default gen_random_uuid(),
  chat_id bigint not null,
  prompt_message_id bigint not null check (prompt_message_id > 0),
  notification_id uuid not null references app.bot_notifications (id) on delete cascade,
  entity_id uuid not null,
  action text not null check (action in ('reject', 'request_changes')),
  state_token text not null check (state_token ~ '^[0-9a-f]{8}$'),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  unique (chat_id, prompt_message_id),
  constraint bot_pending_replies_expiry_after_creation check (expires_at > created_at)
);

create index bot_pending_replies_notification_id_idx
  on app.bot_pending_replies (notification_id);

-- ---------------------------------------------------------------------------
-- Audit of admin decisions, from the admin UI (via the API) and from Telegram.
-- `detail` holds state changes only (e.g. {"from": "in_review", "to": "approved"}),
-- never personal data or free text.
-- ---------------------------------------------------------------------------
create table app.admin_actions (
  id uuid primary key default gen_random_uuid(),
  actor text not null check (actor ~ '^(admin_ui|telegram:[0-9]{1,20})$'),
  action text not null check (action ~ '^[a-z_]{1,40}$'),
  entity_type text not null
    check (entity_type in ('event', 'community_application', 'team_application')),
  entity_id uuid not null,
  detail jsonb not null default '{}'::jsonb
    check (jsonb_typeof(detail) = 'object' and length(detail::text) <= 1000),
  at timestamptz not null default now()
);

create index admin_actions_entity_idx on app.admin_actions (entity_type, entity_id, at);

-- ---------------------------------------------------------------------------
-- Same access model as every app table (01_privileges.test.sql enforces it).
-- ---------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array['bot_state', 'bot_notifications', 'bot_pending_replies', 'admin_actions']
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
