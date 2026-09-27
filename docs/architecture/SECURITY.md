# Security

Reviewed twice: pass 1 = repository and design review, pass 2 = challenge against the Supabase, Vercel and Telegram docs and localhost attack paths.

## 1. Findings in the current repository

| ID | Finding | Severity | Action | Blocks V1? |
|---|---|---|---|---|
| S1 | No `.gitignore` | Medium (becomes High when `.env` files appear) | M0: add `.gitignore` (`.env*` except `.env.example`, `.venv`, `node_modules`, `.next`, `.cache`, `supabase/.temp`) | Yes, first step |
| S2 | `deploy-pages.yml` uploads `path: .` (the whole repo) | Medium | M0: copy only `index.html`, `style.css`, `script.js`, `events.json` to `_site/` and upload that | Yes, before new code lands |
| S3 | Personal email published in HTML and README (scrapable) | Low | Replaced by forms / community links at cutover | No |
| S4 | Git history secret scan | Informational | Pattern scan: clean. Recommend enabling GitHub **secret scanning + push protection** (free for public repos); owner action in repo settings | No |
| S5 | Actions pinned by tag (`@v5`, `@v4`, `@v3`) not SHA | Low (first-party actions) | Keep; workflows are removed at cutover | No |
| S6 | Issue workflow input handling | Good | env-var passing, owner check, least-privilege permissions. Nothing to fix | — |
| S8 | Local Supabase stack publishes ports on `0.0.0.0` (API 54321, DB 54322, Studio 54323, Mailpit 54324), and Windows Firewall has an inbound **Allow, any port** rule for `com.docker.backend.exe` on the **Public** profile. Studio has no auth, and the local DB password is the well-known `postgres`, so the local DB is likely reachable from untrusted Wi-Fi (found 2026-09-28, M2) | High (local data only: seed + test submissions) | Owner decision: (a) set Docker Engine default bind address `"ip": "127.0.0.1"` in Docker Desktop → Settings → Docker Engine (recommended; affects all containers); or (b) disable that firewall rule; (c) meanwhile run `pnpm db:stop` when not developing | No, but fix before real data is copied locally |
| S7 | Legacy frontend rendering | Good | `textContent` + URL allow-list. Keep the same rules in React (no `dangerouslySetInnerHTML` for event data) | — |

## 2. Secrets inventory (target)

| Secret | Lives in | Never in |
|---|---|---|
| Postgres password (`admin_backend`) | `services/api/.env` | git, admin app, Vercel |
| Supabase **publishable** key | Vercel env, `apps/web/.env.local` (server-only usage) | browser bundle (by choice, though it is not secret) |
| Supabase **secret** key | **Not used in V1** | — |
| `ADMIN_API_TOKEN` | `services/api/.env`, `apps/admin/.env.local` | git, Vercel |
| `WEB_REVALIDATE_SECRET` | Vercel env, `services/api/.env` | git |
| `CRON_SECRET` | Vercel env | git, everywhere else |
| Publishable key copy for the keep-alive workflow | GitHub Actions secret `SUPABASE_PUBLISHABLE_KEY` | workflow logs (never `echo`) |
| `TELEGRAM_BOT_TOKEN` | `services/api/.env` | admin app, Vercel, logs, error messages |
| Cloud LLM keys (later) | `services/api/.env` | anywhere else |

Every app ships a committed `.env.example` with names only. The API's error handler redacts values matching known secret names before logging.

## 3. Supabase

- Only the `api` schema is exposed. Tables live in `app`, with RLS enabled and no `anon` policies.
- Legacy JWT keys (`anon`, `service_role`) are **disabled** after setup (they end in 2026 anyway).
- Run `alter default privileges … revoke …` in the first migration, so a future table is never auto-granted to `anon`.
- pgTAP tests assert visibility and privilege rules (DATA_MODEL §4). They run in CI against `supabase start`.
- Check the Supabase security advisor after each migration. The two intentional `security definer` objects are documented.

## 4. Local admin (localhost attack surface)

A malicious website open in the same browser can send requests to `http://localhost:8000` (CSRF) or use DNS rebinding.
- FastAPI binds `127.0.0.1` only, uses `TrustedHostMiddleware` (rejects rebinding hosts), and requires `Authorization: Bearer` on every route except `/health`. A cross-site form cannot set this header.
- No CORS middleware. With no `Access-Control-Allow-Origin`, a browser cannot read responses.
- Admin Next.js binds `127.0.0.1`. Server Actions include Next.js's built-in Origin/Host check.
- Ollama: keep the default localhost binding (do **not** set `OLLAMA_HOST=0.0.0.0`).

## 5. Untrusted content (crawler / LLM)

See CRAWLING_RESEARCH §5 (SSRF, size limits, image handling) and AI_ARCHITECTURE §4 (prompt injection). Summary of the rules:

- Every fetched byte is untrusted: never executed, never used as a file path, never interpolated into SQL (parameterized queries only) or shell.
- A page can never change tools, goals, prompts or secrets. The LLM has no tools and no secrets in context.
- HTML from sources is never rendered as HTML anywhere, only as extracted text.

## 6. Telegram

- Token only in the API env. Requests use `https://api.telegram.org/bot<token>/…`, and the httpx2 client is configured so the URL (which contains the token) is **not logged**.
- Captions are HTML-escaped. Only our template adds tags (`<b>`, `<a href>` with validated URLs).
- The bot has only `can_post_messages` (+ `can_edit_messages`). Other rights are added only when a feature needs them.

## 7. Personal data (community forms)

- Data minimisation: phone only for WhatsApp preference. No IP or user-agent storage.
- The Turkish data protection law (KVKK) likely applies (Turkish residents, a data controller in Türkiye). V1 needs a short privacy notice with purpose, retention (proposed: delete rejected/inactive applications after 12 months) and a deletion contact. **This is not legal advice; the owner must confirm the text** (OPEN_QUESTIONS Q9).
- Supabase region: choose EU (Frankfurt, `eu-central-1`) for latency to Türkiye and GDPR alignment (owner decision at project creation).
- Private tables are readable only by `admin_backend` (the laptop).
