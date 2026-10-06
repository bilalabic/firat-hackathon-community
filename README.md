# Fırat Hackathon Community

A hackathon directory and community platform: discover, verify, structure, review and publish
hackathons, and let students join the community.

> **Live:** https://firat-hackathon-community.vercel.app (the old GitHub Pages URL redirects there). See
> [MASTER_PLAN.md](MASTER_PLAN.md) for progress and [docs/](docs/) for architecture and decisions.

## How it fits together

| Part | Where | Runs on |
|---|---|---|
| Public website (Turkish UI) | `apps/web` (Next.js 16) | Vercel |
| Local admin UI | `apps/admin` (Next.js 16, shadcn dashboard-01) | Developer laptop, `127.0.0.1:3001` |
| Local admin API | `services/api` (FastAPI, Python 3.12) | Developer laptop, `127.0.0.1:8000` |
| Database | `supabase/` (Postgres migrations, pgTAP tests) | Supabase (cloud) / Docker (local) |
| Local LLM (optional) | Ollama | Developer laptop, `127.0.0.1:11434` |

The public site reads published events and submits forms through a narrow `api` schema with the
publishable key. Only the local API writes canonical data. Details:
[SYSTEM_ARCHITECTURE](docs/architecture/SYSTEM_ARCHITECTURE.md).

## Requirements (Windows)

- Node.js ≥ 22 and pnpm 12
- [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`); uv installs Python 3.12
- Docker Desktop (for the local Supabase stack)
- Optional: Ollama (`winget install Ollama.Ollama`) for the LLM check

## Local development

```bash
pnpm install
cd services/api && uv sync && cd ../..

pnpm db:start            # local Supabase (Docker) + backend role login
pnpm db:reset            # recreate the DB: migrations + legacy seed

# env files (gitignored), see each .env.example:
#   services/api/.env      DATABASE_URL, ADMIN_API_TOKEN, ...
#   apps/admin/.env.local  ADMIN_API_URL, ADMIN_API_TOKEN (same token)
#   apps/web/.env.local    SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY (pnpm exec supabase status)

pnpm dev                 # web :3000, admin 127.0.0.1:3001, api 127.0.0.1:8000
pnpm db:stop             # stop the local stack when you are done
```

The local Supabase ports listen on all interfaces (accepted risk, SECURITY S8): stop the stack when
you are not developing.

## Checks

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm build   # all apps + API
pnpm test:db                                             # pgTAP (needs the local stack)
```

`pnpm build` prerenders the public site from the database, so `apps/web/.env.local` must point at a
running Supabase.

## Useful scripts

| Script | Does |
|---|---|
| `pnpm db:types` | Regenerate the web app's types from the `api` schema |
| `pnpm db:legacy-seed` | Regenerate `supabase/seed_legacy_events.sql` from the legacy `events.json` |
| `pnpm --filter admin run api:types` | Regenerate the admin's API types (API running, token required) |

## Legacy site

The old static site was retired at the M7 cutover (2026-10-06). The old GitHub Pages URL now only
redirects to the new site (`pages/`, `.github/workflows/deploy-pages.yml`) and keeps serving the
frozen legacy `events.json` for any external consumer. The legacy data lives in
`supabase/legacy/events.json` and generates `supabase/seed_legacy_events.sql`. The Issue Form flow is
removed; events are added in the local admin.

## Contributing

Open an issue or a pull request on GitHub. Code, docs, database names and the admin UI are in
English; the public UI is in Turkish.
