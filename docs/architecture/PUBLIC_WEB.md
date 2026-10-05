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

The rule is implemented once in `apps/web/src/lib/phase.ts` with unit tests (`phase.test.ts`), including the multi-day case that is broken in the legacy site. An invalid or missing timezone falls back to `Europe/Istanbul`.

### As built (M5)

- Route map: `apps/web/src/lib/routes.ts`; all UI copy: `apps/web/src/lib/copy.ts`.
- List URL state uses Turkish parameter names: `?sekme=yaklasan|acik|son-gunler|gecmis`, `?q=`, `?bicim=yuz-yuze|cevrimici|hibrit`, `?sehir=<city>`. Without `sekme`, the list opens on **Başvurular Açık** if any application is open, otherwise on **Yaklaşan**.
- Search folds Turkish characters like the legacy site (`İ/ı → i`, marks removed, case-insensitive), in `src/lib/search.ts`.
- **Category filter is not in V1**: there is no category vocabulary yet (OPEN_QUESTIONS Q12) and no published event has categories. Format and city filters are implemented.
- `/topluluk` shows no Telegram/WhatsApp links: the channels do not exist yet (Q5, Q13). Invites are sent manually after the form.
- `/katki` "Support the Project" is text only, no donation links (Q3).
- Unknown slugs render the not-found page with `noindex`, but with HTTP 200 (a soft 404): the detail page streams a static shell first, so the status cannot change afterwards (Next.js `notFound()` docs). Unknown paths outside `[slug]` return a real 404. The OG image route returns a real 404 for unpublished slugs.

## 2. Data access

- `@supabase/supabase-js` is created **server-side only** (in a `server-only` module). Env names: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (no `NEXT_PUBLIC_` prefix, so neither is bundled). The browser never receives a Supabase client or key.
- Reads: `from('events_public')` with `db: { schema: 'api' }`.
- Types: `supabase gen types typescript --schema api` → `apps/web/src/lib/database.types.ts` (committed, regenerated per migration).

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
- Search and filters: the published dataset is small (tens to low hundreds). The list page sends the published events once, and filtering happens client-side (like the legacy site). The URL holds filter state (`?sekme=acik&q=ai`, see §1 "As built"). The server also renders the filtered result from the query string (inside a `<Suspense>` boundary, from the same cached data), so a shared link and a no-JavaScript GET form show the same result. Revisit with server-side search if the list grows past about 500 events.
- As built: `src/lib/supabase.ts` (server-only client), `src/lib/events.ts` (`getPublishedEvents`, `getEventListing`, `getEvent`, all `'use cache'` + `cacheLife('hours')`; tags `events`, and `events` + `event:<slug>` for one event).

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
- As built (M5): Server Actions `app/topluluk/actions.ts`, `app/katki/actions.ts` → `src/lib/forms/submit.ts`; zod schemas in `src/lib/forms/schemas.ts` (unit-tested); `consent_version` = `2026-10-community-v1` / `2026-10-team-v1`, set on the server.
  - **Timing:** the page is prerendered, so a server-rendered timestamp would be the build time. Instead the browser measures the fill time (mount → submit, both on the client clock, so clock skew does not matter) and sends `elapsed_ms`; the action rejects values below 3000 ms. The value is not signed: signing needs another server secret and would not stop a bot that calls the RPC directly anyway (R-07). Consequence: the forms need JavaScript.
  - A filled honeypot gets the generic success answer and nothing is stored. A too-fast submission gets an error and nothing is stored. Errors are generic; the RPC error code is logged, never the payload.
  - Submitting goes through `onSubmit` (not the form `action`), so a validation error does not clear what the user typed. Field errors are linked with `aria-describedby`; focus moves to the error summary or the success message.
  - **The KVKK privacy notice is a marked placeholder** (`TASLAK – yayına alınmadan önce onaylanacak`) until the owner approves the text (Q9). The forms must not go live before that.

## 4. SEO and metadata

- `generateMetadata` per event: title, description (= summary), canonical URL, OpenGraph image = card route.
- JSON-LD `schema.org/Event` on detail pages (name, startDate, endDate, eventAttendanceMode, location, organizer, url).
- `sitemap.ts` lists published slugs with `lastModified = updated_at`.
- `lang` attribute follows the chosen UI language (OPEN_QUESTIONS Q1).

## 5. Images

- Organizer posters: external URLs rendered with `next/image` and `remotePatterns` limited to hosts we add explicitly. Fallback: plain `<img>` with `referrerPolicy="no-referrer"`, to stay inside the Hobby image quota (5,000 transformations/month).
- Card: `opengraph-image.tsx` with Geist `.ttf` (Satori does not read `woff2`). Turkish glyphs (ı ş ğ İ) must be checked in the M5 review.
- As built (M5): `Geist-Regular.ttf` and `Geist-SemiBold.ttf` are vendored in `apps/web/assets/fonts/` with the OFL license, copied unmodified from the npm package `geist@1.7.2` (published from the official `vercel/geist-font` repo; checksums in `assets/fonts/README.md`). Vendoring two files was chosen over a dependency so the image route reads a fixed path. The card shows only stored facts (title, organizer, deadline, dates, place), never the phase or "days left", so it is deterministic. Turkish glyphs were checked on rendered PNGs in M5. Posters use a plain `<img referrerPolicy="no-referrer">`; `remotePatterns` is empty.

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
