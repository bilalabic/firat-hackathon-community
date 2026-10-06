# Telegram as an Admin Control Surface

Research date: 2026-10-06. Source: Bot API 10.3 (`https://core.telegram.org/bots/api`, 2026-08-24) and the
Mini Apps docs (`https://core.telegram.org/bots/webapps`). Question from the owner: can approvals and
similar admin decisions be handled from Telegram instead of the local admin UI?

## 1. Verified platform facts

| Need | Bot API facility | Verified detail |
|---|---|---|
| Buttons on a message | Inline keyboard `InlineKeyboardButton.callback_data` | **1–64 bytes** per button |
| Receive button presses | `CallbackQuery` update (`from`, `message`, `data`) | Delivered via getUpdates or webhook |
| Acknowledge a press | `answerCallbackQuery` | Shows a notification/alert to the presser. We call it for every press (Telegram's recommended practice; the exact client behavior was not re-verified) |
| Update the buttons after a decision | `editMessageReplyMarkup` / `editMessageText` | No time limit for the bot's own messages (the 48 h rule applies to business messages) |
| Receive updates without a public server | `getUpdates` long polling (`timeout` > 0, `offset`, `allowed_updates`) | An update counts as confirmed once `offset` moves past it |
| Retention when nobody polls | — | "Incoming updates are stored on the server until the bot receives them … but they will not be kept longer than **24 hours**" |
| Receive updates on a server | `setWebhook` with `secret_token` | Sent back in the `X-Telegram-Bot-Api-Secret-Token` header; HTTPS only; ports 443, 80, 88, 8443. **While a webhook is set, getUpdates does not work** |
| Full UI inside Telegram | Mini Apps (`web_app` buttons, private chats only) | The server validates `Telegram.WebApp.initData` with HMAC-SHA256, using a key derived from the bot token with `"WebAppData"`. It should also check `auth_date` for freshness. **It needs a public HTTPS page** |

## 2. Options

### A. Local long-polling bot inside the admin API (recommended for V1.1)

The FastAPI process polls `getUpdates`, sends notifications (e.g. "new event in review", "new
application"), and executes button presses through the **existing service layer**: the same state
machine, guards and revalidation as the admin UI.

- Fits the architecture: the bot token stays on the laptop, there is no new internet-facing endpoint,
  there is still exactly one writer of canonical data (D-05), and Vercel keeps only the publishable
  key (D-08).
- No extra cost or infrastructure.
- **Limitation:** actions only run while the laptop and API are on. Presses made while it is off are
  delivered when it comes back, if that is within 24 h. Stale presses are therefore rejected
  (see §4).

### B. Cloud webhook (Vercel route handler or Supabase Edge Function)

Works 24/7, but:

- it needs **write access** to `app.*` in the cloud: a secret key or a new privileged role on
  Vercel/Supabase. That breaks D-08 and turns the public site into an admin entry point;
- the state machine, guards and revalidation would need a second implementation in TypeScript/Deno,
  so there would be two writers with rules that can drift;
- it adds a public endpoint whose only protection is the `secret_token` header plus the user
  allowlist.

**Not recommended now.** Revisit if the laptop being off becomes a real bottleneck. At that point,
moving the whole API to a small always-on host is cleaner than splitting the logic.

### C. Telegram Mini App (the admin UI inside Telegram)

The richest UX, but it requires hosting the admin UI publicly over HTTPS. That reverses the
local-only decision (D-04/D-05) and needs a real authentication design (initData validation plus an
allowlist on every request). **Reject for V1.x**; reconsider together with B.

## 3. Proposed scope (Option A)

| Flow | Telegram message | Buttons |
|---|---|---|
| Event submitted for review | Title, dates, deadline, format/location, official URL, and **deterministic review signals** (✓/✗ list, no scores) | **Approve** · **Request changes** · **Reject** |
| Event approved | Short summary | **Publish** (two-step confirm) · Later |
| Published event changed | "changed since published" (V1.1 publication hash) | Repost/edit Telegram post (with V1.1 channel publishing) |
| New community/team application | Count + first name + chosen channel. **No phone number or full details** (§5) | Contacted · Accepted · Declined · Spam |
| Daily digest (optional) | Counts: in review, closing in 7 days, stale heartbeats | — |

Text input (rejection reason, change request) uses the reply-to-message pattern: the bot sends
"Reply with the reason" and the next reply from the admin in that chat completes the action.

Event editing stays in the admin UI. Telegram is for **decisions**, not data entry.

## 4. Security design

1. **Admin allowlist:** `TELEGRAM_ADMIN_USER_IDS` (numeric user ids, not usernames). Updates from
   anyone else are ignored and logged at warning level without content. Only the private chat with
   the bot is used. The bot is not added to groups for admin purposes.
2. **Stale and replayed presses:** `callback_data` = `v1:<action>:<event id, 32 hex>:<4-char
   state token>`, ≤ 64 bytes. The state token is derived from the event's `updated_at`, so a press
   is executed only if the event has not changed since the message was sent. Otherwise the bot
   answers "Outdated, here is the current state". Presses older than a configurable age (default
   12 h) are refused.
3. **Destructive and public actions need two steps:** Publish and Reject replace the keyboard with
   "Confirm / Cancel".
4. **Idempotency:** the last processed `update_id` is persisted (small `app.bot_state` row), so a
   restart never re-processes updates. State transitions are already idempotent-safe: an invalid
   transition returns 409.
5. **Audit:** every bot action records the actor (`telegram:<user id>`), action, event and time.
   Recommended: a new `app.admin_actions` table, also used by the admin UI.
6. **Token handling:** same rules as today (only in `services/api/.env`, redacted from logs). If the
   token leaks, an attacker could read the bot's chat but **cannot impersonate the admin's button
   presses**. Rotate via @BotFather. Optional: a separate admin bot so the public channel bot never
   sees admin traffic.
7. **Prompt-injection relevance:** event text shown in Telegram messages is HTML-escaped (existing
   `telegram/formatting.py`). Nothing from Telegram is ever passed to an LLM as instructions.

## 5. Personal data (KVKK)

Messages are stored on Telegram's servers, outside Türkiye. Sending applicants' personal data
(phone, Telegram username, message) to the admin chat is a transfer of personal data to a third
party.

- Default: send counts and first names only, with the status buttons. Read full details in the admin
  UI.
- If full details are wanted in Telegram, the privacy notice (Q9) must say so.

## 6. Effort and placement

- Fits into **V1.1** next to channel publishing, which uses the same bot client.
- Split V1.1 into **V1.1a** (channel publishing) and **V1.1b** (admin approvals via the bot).
- Building blocks already exist: Telegram client (M6), state machine and review signals (M3), HTML
  escaping.
- New work:
  - polling loop: a lifespan background thread with backoff;
  - send/edit methods;
  - callback router;
  - `app.bot_state` and `app.admin_actions` (one migration);
  - tests with MockTransport;
  - a Settings card showing bot status.
- Rough size: similar to M6 (one subagent plus a review).

## 7. Decisions needed

See `docs/planning/DECISIONS.md` **D-21** (proposed) and `OPEN_QUESTIONS.md` Q14–Q16.

## 8. As built (V1.1b, 2026-10-06)

Implementation: `services/api/src/fhc_api/admin_bot/` (details in `docs/architecture/LOCAL_ADMIN.md`,
"Telegram admin bot"). Differences from the proposal above, and facts re-checked against Bot API 10.3:

- **State token:** 8 hex characters (not 4), from SHA-256 of the entity's `updated_at` (the
  migration adds `updated_at` to the application tables). `callback_data` is at most 50 bytes.
- **Press age:** `CallbackQuery` carries no press time, so the age is that of the bot's message
  (`sent_at` in `app.bot_notifications`, database clock). An expired press is refused, and each
  scan also retires unpressed messages past the limit; a fresh message with new buttons follows.
- **Reject:** Reject → Confirm / Cancel → reason prompt (`force_reply`, reply within 15 min).
  Request changes → reason prompt directly. Publish → Confirm / Cancel. The confirmation stage
  is recorded server-side, so a crafted Confirm button without the first press is refused.
- **Stale messages are retired proactively:** each scan edits messages whose entity changed elsewhere
  (admin UI, another admin) to remove their buttons.
- **Re-checked (2026-10-06):** `getUpdates` `offset`/`timeout`/`allowed_updates` semantics;
  `CallbackQuery.message` is a `MaybeInaccessibleMessage` (`date` 0 when inaccessible);
  `answerCallbackQuery` `text` 0–200 characters; `ForceReply.input_field_placeholder` 1–64
  characters; `sendMessage` `text` 1–4096 characters, `reply_parameters`, `link_preview_options`;
  `editMessageText` / `editMessageReplyMarkup` return the edited `Message`.
- **Not re-verified, to confirm in the real-bot E2E (B5):** that `editMessageText` without
  `reply_markup` removes the inline keyboard (relied on for outcome edits), and the exact client
  display of callback answers.
