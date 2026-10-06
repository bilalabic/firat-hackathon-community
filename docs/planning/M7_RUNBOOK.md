# M7 Runbook: Cloud Setup and Cutover

Run step by step and record results in `MASTER_PLAN.md`. Steps marked **(owner)** need the owner's
accounts or decisions. Nothing here may use `supabase db push --include-seed` except step 3.4.

## 0. Prerequisites (owner)

- [ ] Supabase account; GitHub account connected to Vercel.
- [ ] Decide the public URL: `<project>.vercel.app` now, custom domain later (Q4).
- [ ] KVKK privacy notice text approved (Q9). **The forms must not go live with the TASLAK
  placeholder.** Until it is approved, either keep the forms disabled or do not announce the site.
- [ ] Logins on the dev laptop: `pnpm exec supabase login` and `pnpm dlx vercel login`.

## 1. Supabase project (owner creates, orchestrator configures)

1. Create the project on the **Free** plan, region **Frankfurt (eu-central-1)**. Store the DB
   password in a password manager.
2. Settings → API Keys: create the **publishable** and **secret** keys. The secret key is not used
   in V1. **Disable the legacy `anon`/`service_role` keys** once nothing uses them.
3. Settings → Data API: **exposed schemas = `api` only** (`db push` does not carry
   `config.toml [api]`; alternatively `supabase config push`).
4. Authentication → disable sign-ups.

## 2. Schema

1. `pnpm exec supabase link --project-ref <ref>`
2. `pnpm exec supabase db push` (migrations only, no seed).
3. Verify in the SQL editor (or via `psql`):
   - `select * from pg_default_acl` → compare with local;
   - the Security Advisor shows only the documented, intentional security-definer objects.

## 3. Backend role and data

1. SQL editor: `alter role admin_backend with login password '<generated, 32+ chars>';`
2. Laptop `services/api/.env`: `DATABASE_URL=postgresql://admin_backend.<ref>:<password>@<pooler-host>:5432/postgres?sslmode=require`
   (session pooler). **Verify that the pooler accepts the custom role** (`GET /system/db` via the
   admin Settings page). Fallback: direct connection if the network has IPv6.
3. Keep a local copy of `services/api/.env` in the password manager.
4. One-time legacy import: run `supabase/seed_legacy_events.sql` once in the SQL editor
   (idempotent, `on conflict do nothing`). Then add any events created since in the admin.

## 4. Vercel (owner connects, orchestrator verifies)

1. New project from the GitHub repo; **Root Directory `apps/web`**, framework Next.js.
2. Environment variables (Production, and Preview where noted):
   - `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (Production + Preview; the build prerenders from the DB)
   - `NEXT_PUBLIC_SITE_URL` (the final public URL)
   - `WEB_REVALIDATE_SECRET` (random 32+ chars; same value in `services/api/.env`)
   - `CRON_SECRET` (random 16+ chars)
3. Deploy. Confirm that the cron job `/api/cron/keep-alive` appears under Settings → Cron Jobs.
4. Laptop `services/api/.env`: `WEB_BASE_URL=<public URL>`, `WEB_REVALIDATE_SECRET=<same>`.

## 5. Keep-alive (D-19)

1. GitHub → Settings → Secrets and variables → Actions: `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`.
2. Actions → "Supabase keep-alive" → Run workflow → green; `app.heartbeats` gets `github_actions`.
3. The next day: both heartbeats are fresh on the admin Overview.

## 6. Verification (MVP criteria)

- [ ] **#6:** `curl` with the publishable key: `events_public` returns rows, `community_applications`
  fails, and a request **without** `apikey` gets 401.
- [ ] **#12:** publish in the admin, then the event appears on the site within seconds; unpublish removes it.
- [ ] **#13:** with the laptop off, the site and forms work.
- [ ] **#15:** one test form submission (prefix `ZZ Prod Test`), then delete it in the admin/SQL.
- [ ] **#16:** detail page metadata, OG card (Turkish glyphs) and sitemap on the real URL.
- [ ] **#17:** Lighthouse mobile on `/hackathonlar` ≥ 95 for Performance, Accessibility and SEO.
- [ ] **#8:** the deployed client bundle contains no secrets.
- [ ] **#21:** both heartbeats are recorded; an unauthorized cron call gets 401.

## 7. Cutover (done 2026-10-06)

1. Replace the legacy site on GitHub Pages with a small page: a meta refresh plus a link to the new
   URL (keep `deploy-pages.yml` publishing just that page).
2. Remove the Issue Form automation: `.github/workflows/add-event.yml`,
   `.github/scripts/add_event.py`, `.github/ISSUE_TEMPLATE/event.yml`; point
   `.github/ISSUE_TEMPLATE/config.yml` to the new community page.
3. Move `index.html`, `style.css`, `script.js` and `events.json` out of the root (delete them; git
   history keeps them, and the seed was generated from `events.json`).
4. Update README "Legacy site" and `MASTER_PLAN.md`.

## Rollback

- Site broken: in Vercel, use Instant Rollback to the previous deployment.
- Cutover regretted: revert the cutover PR; Pages redeploys the legacy site.
- Data problem: Supabase Free has no point-in-time recovery. Before step 7, export with
  `pnpm exec supabase db dump --data-only` and keep the file outside the repo.
