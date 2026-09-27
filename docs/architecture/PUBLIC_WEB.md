# Public Website

`apps/web`: Next.js 16 (App Router, Cache Components), TypeScript, Tailwind, shadcn/ui, Geist, Lucide. Deployed to **Vercel** (project root directory `apps/web`).

It is a hackathon directory and community portal, and **does not** use the dashboard layout. The inspiration is Vercel/Linear/Luma/GitHub in terms of restraint (typography, whitespace, content first). We do not copy any of them.

## 1. Information architecture and routes

| Route | Content | V1 |
|---|---|---|
| `/` | Hero line + "Applications open" and "Closing soon" sections + link to all | ✔ |
| `/hackathons` | Full list; tabs **Upcoming · Applications open · Closing soon · Past**; text search; filters: format, city, category | ✔ |
| `/hackathons/[slug]` | Detail: dates, deadline countdown, format/location, team size, eligibility, prize, official + apply buttons, "last updated" | ✔ |
| `/hackathons/[slug]/opengraph-image` | 1200×630 PNG card (Satori). Also used as the Telegram image | ✔ |
| `/community` | Why join, Telegram link, WhatsApp info, **Join Community** form | ✔ |
| `/contribute` | Four separate intents: **Join the Team** (form), **Contribute Code** (GitHub link + good-first-issues), **Support the Project** (text only in V1), **Suggest an event** (link to the community channel / email) | ✔ |
| `/about` | Mission, who runs it, contact | ✔ |
| `/sitemap.xml`, `/robots.txt` | via `app/sitemap.ts`, `app/robots.ts` | ✔ |
| `/api/revalidate` | `POST`, header `Authorization: Bearer <WEB_REVALIDATE_SECRET>`, body `{tags: string[]}` | ✔ |
| `/api/cron/keep-alive` | `GET` from Vercel Cron (daily), requires `Authorization: Bearer <CRON_SECRET>`, calls `api.keep_alive('vercel_cron')`. It reads request headers, so it is never prerendered or cached | ✔ |

**Language (D-18):** the public UI is Turkish-first: `<html lang="tr">`, Turkish labels, `Intl.DateTimeFormat('tr-TR')`. The paths above are the English code names; the public URL segments are Turkish (`/hackathonlar`, `/topluluk`, `/katki`, `/hakkinda`), defined in one route map. Every UI string lives in `lib/copy.ts`.

### Phase rules (computed, in the event timezone, "today" = local date)

| Phase | Rule |
|---|---|
| Applications open | `deadline ≥ today` |
| Closing soon | open **and** `deadline − today ≤ 7 days` (subset of open, shown as a badge + tab) |
| Upcoming | not open, and `(end_date ?? start_date) ≥ today` |
| Past | `(end_date ?? start_date) < today` |
| Undated | no dates → listed under Upcoming with "Dates TBA" |

The rule is implemented once in `apps/web/lib/phase.ts` with unit tests, including the multi-day case that is broken in the legacy site.

## 2. Data access

- `@supabase/supabase-js` is created **server-side only** (in a `server-only` module). Env names: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (no `NEXT_PUBLIC_` prefix, so neither is bundled). The browser never receives a Supabase client or key.
- Reads: `from('events_public')` with `db: { schema: 'api' }`.
- Types: `supabase gen types typescript --schema api` → `apps/web/lib/database.types.ts` (committed, regenerated per migration).

### Caching

```ts
async function getPublishedEvents() {
  'use cache'
  cacheLife('hours')      // time-based fallback if revalidation never arrives
  cacheTag('events')
  ...
}
```

- `cacheComponents: true`.
- FastAPI calls `/api/revalidate` with tags `['events', 'event:<slug>']` after publish, unpublish or edit. The handler calls `revalidateTag(tag, { expire: 0 })`.
- If the laptop is off, nothing breaks. Content is at most `cacheLife` old, and phases shift at most an hour late.
- Phase computation depends on "today". It runs at render inside the cached function, so drift is bounded by `cacheLife('hours')`. This is acceptable.
- Search and filters: the published dataset is small (tens to low hundreds). The list page sends the published events once, and filtering happens client-side (like the legacy site). The URL holds filter state (`?tab=open&q=ai`). Revisit with server-side search if the list grows past about 500 events.

## 3. Forms (Join Community, Join the Team)

```text
<form> (Client Component, react-hook-form optional; native validation + zod)
  → Server Action
      1. honeypot field must be empty; reject if submitted < 3 s after render (timestamp field)
      2. zod validation (same limits as DB)
      3. supabase.schema('api').rpc('submit_community_application', { payload })
      4. return generic success; never echo stored data
```

- Consent checkbox with a versioned notice (`consent_version`, e.g. `2026-10-community-v1`). The text explains purpose, retention and deletion contact (KVKK: see SECURITY §7).
- Community intake happens through this form, for both Telegram and WhatsApp (owner confirmed 2026-09-28). The form collects the participant's preferred channel. Phone (E.164, Turkish numbers normalised from `05xx…` to `+905xx…`) is asked **only** if the preferred channel is WhatsApp. Telegram username is asked only for Telegram. The admin then sends the invite link manually in V1. Automated invites/join-request approval are V2.
- Rate limiting: V1 relies on honeypot + timing + DB constraints. If spam appears, add Cloudflare Turnstile verified in the Server Action (V1.x).
- Known limitation: the publishable key allows calling the RPC directly and bypassing the honeypot. The impact is spam only, never data exposure. This is accepted for V1 (see RISKS R-07).

## 4. SEO and metadata

- `generateMetadata` per event: title, description (= summary), canonical URL, OpenGraph image = card route.
- JSON-LD `schema.org/Event` on detail pages (name, startDate, endDate, eventAttendanceMode, location, organizer, url).
- `sitemap.ts` lists published slugs with `lastModified = updated_at`.
- `lang` attribute follows the chosen UI language (OPEN_QUESTIONS Q1).

## 5. Images

- Organizer posters: external URLs rendered with `next/image` and `remotePatterns` limited to hosts we add explicitly. Fallback: plain `<img>` with `referrerPolicy="no-referrer"`, to stay inside the Hobby image quota (5,000 transformations/month).
- Card: `opengraph-image.tsx` with Geist `.ttf` (Satori does not read `woff2`). Turkish glyphs (ı ş ğ İ) must be checked in the M5 review.

## 6. Accessibility and performance targets

WCAG 2.2 AA contrast, keyboard navigation, visible focus, `prefers-reduced-motion`. Lighthouse ≥ 95 for Performance, Accessibility and SEO on `/hackathons` (mobile).

## 7. Environment (Vercel)

| Name | Scope |
|---|---|
| `SUPABASE_URL` | Production + Preview |
| `SUPABASE_PUBLISHABLE_KEY` | Production + Preview |
| `WEB_REVALIDATE_SECRET` | Production |
| `CRON_SECRET` | Production (Vercel sends it to the cron endpoint automatically) |
| `NEXT_PUBLIC_SITE_URL` | Production + Preview |

No secret Supabase key, Telegram token or LLM key is stored in Vercel.
