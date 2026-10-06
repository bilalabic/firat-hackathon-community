# V1.1b: Admin Decisions via Telegram

Status: **approved by the owner (2026-10-06)**. Decision: D-21 option A. Research:
`docs/research/TELEGRAM_ADMIN_RESEARCH.md`.

## Goal

The owner can review and decide on events and applications from Telegram while the local admin API
is running, with the same rules as the admin UI. Editing stays in the admin UI.

## Owner decisions (2026-10-06)

| Topic | Decision |
|---|---|
| Architecture | Long-polling bot inside the local admin API (no webhook, no public endpoint) |
| Actions (Q14) | Event: Approve, Request changes (reason), Reject (reason, confirm), Publish (confirm). Application: Contacted, Accepted, Declined, Spam |
| Bot (Q15) | A **separate admin bot** (token `TELEGRAM_ADMIN_BOT_TOKEN`), distinct from the future channel-publishing bot |
| Personal data (Q16) | Application notifications carry **first name + chosen channel + type only**; no phone, username or message |
| Bot language | English (same as the admin UI, D-18) |

## Design

### Components (`services/api/src/fhc_api/admin_bot/`)

| Part | Responsibility |
|---|---|
| `settings` | `TELEGRAM_ADMIN_ENABLED` (default false), `TELEGRAM_ADMIN_BOT_TOKEN`, `TELEGRAM_ADMIN_USER_IDS` (numeric ids), `TELEGRAM_ADMIN_MAX_PRESS_AGE_H` (default 12), `TELEGRAM_ADMIN_SCAN_INTERVAL_S` (default 60) |
| `runner` | Background thread started/stopped by the app lifespan when enabled. Long polling (`getUpdates`, `timeout` ≈ 30 s, `allowed_updates` = message, callback_query) with exponential backoff. Persists the update offset. Never crashes the API |
| `outbox` | Every scan interval: (1) events in `in_review` without a current notification, (2) `approved` events without a publish prompt, (3) `new` applications not yet notified. Sends one message each, recorded in `app.bot_notifications`. Uses a re-notification guard so a message is never sent twice |
| `codec` | `callback_data` = `v1:<action>:<entity type>:<id 32 hex>:<state token>`, ≤ 64 bytes; state token = short hash of the entity's `updated_at` (events) or `status` (applications). Unit-tested size and round-trip |
| `handlers` | Allowlist check, then: stale check (state token and press age), two-step confirm for Publish/Reject, reason capture via `force_reply` (the pending prompt is stored), execution through the **existing** `events` / `community` services (same guards, revalidation, 409 handling), answer callback, edit the message to show the result and remove buttons |
| `messages` | HTML-escaped text built with `telegram/formatting.py`. Events: title, dates, deadline, format/location, official URL, deterministic review signals (✓/✗). Applications: type, first name, channel |
| `whoami` CLI | `uv run python -m fhc_api.admin_bot.whoami`: reads pending updates once and prints the numeric ids of users who messaged the bot, so the owner can fill `TELEGRAM_ADMIN_USER_IDS` |

### Telegram client additions (`telegram/client.py`)

`get_updates`, `send_message` (with inline keyboard / force_reply), `edit_message_text`,
`edit_message_reply_markup`, `answer_callback_query`. Same token-redaction guarantees as M6.

### Database (one migration)

| Table | Purpose |
|---|---|
| `app.bot_state` | Key/value (e.g. `admin_bot.update_offset`) |
| `app.bot_notifications` | `entity_type`, `entity_id`, `kind` (`review` / `publish` / `application`), `state_token`, `chat_id`, `message_id`, `sent_at`, `resolved_at`, `resolution` |
| `app.bot_pending_replies` | Reason prompts awaiting a reply: `chat_id`, `prompt_message_id`, `entity_id`, `action`, `expires_at` |
| `app.admin_actions` | Audit: `actor` (`telegram:<id>` / `admin_ui`), `action`, `entity_type`, `entity_id`, `detail`, `at`. Written by the bot **and** by the admin API for transitions and application status changes |

All tables: RLS on, `admin_backend` policy, no API-role access (enforced by the existing catalog
tests in `01_privileges.test.sql`).

### Admin UI / API

- `GET /admin-bot/status`: enabled, running, last poll time, last error (no secrets), allowlist size, pending notifications.
- A Settings card for it.

## Acceptance criteria

1. With `TELEGRAM_ADMIN_ENABLED=false` (the default) nothing starts and no Telegram call is made. A bad token or config never stops the API (same as M6).
2. Presses from a user id not in the allowlist do nothing, are answered with a generic "not allowed", and are logged without content.
3. An event entering `in_review` (from any path) produces exactly one Telegram message within one scan interval. A restart does not duplicate it.
4. Approve / Request changes / Reject / Publish from Telegram produce the same state, timestamps, notes and revalidation as the admin UI. Invalid or stale presses change nothing and say why.
5. Publish and Reject require a second confirmation press. Reject and Request changes capture the reason from a reply.
6. Application notifications contain no phone number, Telegram username or message text.
7. Every executed action has an `app.admin_actions` row; the admin UI's transitions and status changes are audited too.
8. The token never appears in logs, errors or API responses.
9. Tests: unit tests (codec, stale checks, allowlist, message building, redaction) and integration tests with MockTransport + rolled-back DB transactions. pgTAP tests still pass with the new tables.
10. E2E on the real bot (after the owner creates it): one event through review → approve → publish from a phone; one application status change.

## Owner tasks (parallel)

1. In Telegram, open **@BotFather** → `/newbot` → name e.g. "FHC Admin" → copy the token.
2. Put it **directly into** `services/api/.env` as `TELEGRAM_ADMIN_BOT_TOKEN=...` (do not paste it into chat).
3. Send `/start` to the new bot from your account. The `whoami` helper then prints your numeric id for `TELEGRAM_ADMIN_USER_IDS`.

## Milestones

| Step | Who |
|---|---|
| B1: migration + Telegram client additions + codec/messages (unit tested) | subagent (builder) |
| B2: runner, outbox, handlers, audit in admin API, status endpoint + Settings card | same builder |
| B3: independent review | subagent (reviewer) |
| B4: fixes, orchestrator verification, merge, `supabase db push` to cloud | orchestrator |
| B5: real-bot E2E with the owner | orchestrator + owner |
