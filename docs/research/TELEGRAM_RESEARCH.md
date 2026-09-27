# Telegram Research

Source: official Bot API docs `https://core.telegram.org/bots/api` (current: **Bot API 10.3, 2026-08-24**) and Bot FAQ `https://core.telegram.org/bots/faq`. Checked 2026-09-27.

## 1. Verified capabilities and limits

| Need | Method | Verified limit / rule |
|---|---|---|
| Validate token | `getMe` | — |
| Validate channel + bot rights | `getChat`, `getChatMember` | Bot must be an administrator to post in a channel |
| Text post | `sendMessage` | text **1–4096** chars after entity parsing |
| Image post | `sendPhoto` | caption **0–1024** chars; upload ≤ **10 MB**; by URL ≤ **5 MB**; width + height ≤ 10000; aspect ratio ≤ 20 |
| Album | `sendMediaGroup` | 2–10 items |
| Edit text | `editMessageText` | No time limit for the bot's own channel posts (the 48 h limit applies to *business* messages) |
| Edit caption | `editMessageCaption` | Same as above |
| Replace image | `editMessageMedia` | Can also turn a text message into a media message |
| Delete | `deleteMessage` | General rule: "can only be deleted if it was sent less than 48 hours ago". Separately: "If the bot has `can_delete_messages` … in a channel, it can delete any message there". **See INVESTIGATE T-1.** |
| Message identity | Response `Message.message_id` + `chat.id` | Store both; `message_id` is unique only within a chat |
| Invite links | `createChatInviteLink` (`name` 0–32 chars, `expire_date`, `member_limit`, `creates_join_request`) | Bot must be an admin with the appropriate rights |
| Join requests | `chat_join_request` update, `approveChatJoinRequest` | Requires the `can_invite_users` admin right |
| Receiving updates | `getUpdates` **or** webhook | Mutually exclusive: while a webhook is set, `getUpdates` does not work |
| Rate limits (FAQ) | — | ~1 msg/s per chat; ≤ 20 msg/min in a group; ~30 msg/s broadcast. Paid broadcasts need large Star balances, so they are not relevant. |
| File limits (FAQ) | — | Download 20 MB, upload 50 MB (cloud Bot API) |

## 2. Implications for our design

1. **No webhook is needed.** The admin runs only on a laptop. Publishing is outbound (`send*`, `edit*`). If join requests are used later, the local backend can long-poll `getUpdates`. Nothing has to be exposed to the internet.
2. **Caption budget is 1024 characters.** The standard post is `sendPhoto` (event card) with a caption ≤ 1024. The template must be designed for this budget. If the copy is longer, fall back to `sendMessage` with a link preview. Do not split one event into two messages.
3. **Editing is possible without time limits** for channel posts, so the "event changed after publication" flow can edit the original post. For material changes (dates, deadline) the default is edit + short "Updated:" line. A new post is used only when the owner chooses it.
4. **Image by URL** (≤ 5 MB): the event card can be the public site's OpenGraph image URL (see AI_ARCHITECTURE / SYSTEM_ARCHITECTURE for the image decision). Upload (≤ 10 MB) is the fallback when the URL fetch fails.
5. **Library choice:** we need about 7 endpoints. We call the HTTP API directly with `httpx2` and Pydantic models for the responses. We do not add `python-telegram-bot` or `aiogram`, which are built for interactive bots with handlers and dispatchers. Revisit if we build interactive bot commands.
6. **Formatting:** use `parse_mode=HTML` with a strict escaping function (`&`, `<`, `>` only). HTML is easier to escape correctly than MarkdownV2, which has about 18 reserved characters.

## 3. Open items

- **T-1 (INVESTIGATE, V1.1):** whether the 48 h delete rule applies to a bot with `can_delete_messages` in a channel. The docs list both statements. Test on a private test channel before relying on delete. Edit is the primary correction path anyway.
- **T-2 (resolved 2026-09-28):** No channel exists yet; the owner will create one. See §4.
- **T-3:** Bot token storage: only in `services/api/.env` (gitignored). Never in the admin Next.js app, never in Vercel.

## 4. Setup checklist (owner, before M6)

1. Create a **channel** (announcements). A discussion group is optional and can be linked to the channel later.
2. Choose public (`@username`) or private. A public username makes the ID simple (`@name`). A private channel uses the numeric `-100…` id, which `getChat` / the first update reveals.
3. Create the bot with **@BotFather** (`/newbot`). Store the token only in `services/api/.env`.
4. Add the bot to the channel as **administrator** with only *Post messages*, *Edit messages of others* and *Delete messages of others*.
5. Run the admin **Settings → Test Telegram** check (M6). It calls `getMe`, `getChat` and `getChatMember` and reports missing rights.

A private test channel with the same bot is recommended for V1.1 development, so tests never post to the real audience.
