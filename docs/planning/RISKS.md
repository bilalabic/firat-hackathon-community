# Risks

| ID | Risk | Likelihood | Impact | Mitigation | Owner/Version |
|---|---|---|---|---|---|
| R-01 | Supabase Free project paused after 7 days of low activity → public site loses data | Low (after D-19) | High | Two independent daily schedulers (Vercel Cron + GitHub Actions, 12 h apart), heartbeat shown in admin, Supabase warning email ~1 week before pause; restore possible within 1 year; Pro as fallback | V1 M5/M7 |
| R-17 | GitHub disables scheduled workflows in public repos after 60 days without repo activity | Medium | Low (secondary pinger) | Vercel Cron is primary; heartbeat turns red after 48 h; re-enable with one click or any commit | V1 M7 |
| R-18 | Supabase treats synthetic keep-alive as non-genuine activity in future terms | Low | High | Keep-alive does a real read and a write; monitor Supabase terms; Pro fallback | Ongoing |
| R-02 | Supabase legacy keys end 2026; tutorials still use them | High if ignored | High | Use publishable key + direct DB role from day one; disable legacy keys | V1 M2 |
| R-03 | Security-definer view/functions misconfigured → private data exposed | Low | Critical | pgTAP privilege tests in CI; manual curl check (MVP #6); advisor review | V1 M2 |
| R-04 | Local API abused from browser (CSRF / DNS rebinding) | Low | High | 127.0.0.1 bind, TrustedHost, bearer token, no CORS | V1 M3 |
| R-05 | Toolchain setup friction on new machines | Low | Medium | Resolved on the dev laptop (uv 0.12.16, Python 3.12.14, Ollama 0.34.2 installed 2026-09-28); README documents winget steps; `uv` pins Python | V1 M1 |
| R-06 | Two runtimes increase maintenance for a small team | Medium | Medium | Strict boundary (FastAPI writes, Next.js renders); no shared packages; one `pnpm dev` | Ongoing |
| R-07 | Form spam via direct RPC calls | Medium | Low | Honeypot, timing, DB constraints, `spam` status; add Turnstile if it happens | V1.x |
| R-08 | Personal data handling (KVKK) | Medium | High | Minimal fields, consent versioning, retention policy, deletion contact; owner confirms text | V1 M5 |
| R-09 | Small local models extract wrong dates | High | High | Evidence snippets + deterministic checks + mandatory human review; benchmark gate | V1.2 |
| R-10 | Undocumented Devpost endpoint changes or ToS disallows use | Medium | Medium | Treat as optional source, fail closed, ToS review before automation | V1.4 |
| R-11 | Prompt injection in event pages | Medium | Medium | No tools/secrets in LLM context, schema-only output, human preview (AI_ARCHITECTURE §4) | V1.2 |
| R-12 | Vercel Hobby non-commercial restriction vs "Support the Project" | Low | Medium | Keep support section informational; owner confirms (Q3) | V1 M5 |
| R-13 | Cache Components is a new model; examples online use old caching | Medium | Low | Follow 16.x docs; review checklist item | V1 M5 |
| R-14 | Cutover breaks the only working publishing path | Low | Medium | Legacy flow kept until web + admin pass acceptance; cutover is the last milestone | V1 M7 |
| R-15 | Telegram delete limits unclear (48 h) | Medium | Low | Edit is primary correction; test on a private channel (T-1) | V1.1 |
| R-16 | Laptop is a single point for admin work (no backup of local-only state) | Medium | Low | No canonical data is local; only `.env` files — keep a password-manager copy | V1 |
| R-19 | Local Supabase stack reachable from the LAN (0.0.0.0 bindings + Docker firewall allow rule on Public profile) | Medium | High (local data) | SECURITY S8: bind Docker to 127.0.0.1 or disable the rule; stop the stack when idle | Accepted by owner 2026-09-28 |
