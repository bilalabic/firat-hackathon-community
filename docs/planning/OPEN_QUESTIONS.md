# Open Questions

## Resolved (2026-09-28)

| ID | Question | Answer |
|---|---|---|
| Q1 | Public UI language | Turkish-first public UI; code, docs and admin in English (D-18) |
| Q2 | Supabase plan | Free plan, must not pause → redundant keep-alive (D-03, D-19). Region still to choose at project creation (recommend Frankfurt `eu-central-1`) |
| Q5 | Telegram channel | Does not exist yet; owner will create it (steps in TELEGRAM_RESEARCH §4). Needed before M6 |
| Q6 | Collect participants via web form, including WhatsApp phone? | Yes: one Join Community form. Phone only when WhatsApp is the preferred channel |
| Q7 | Install `uv` and Ollama on Windows | Approved (D-13) |
| — | Version order | Telegram V1.1, discovery V1.4 (D-11) |
| Q14 | Telegram admin actions | Approve / Request changes / Reject / Publish (confirm) + application status (2026-10-06) |
| Q15 | One or two bots | Separate admin bot (2026-10-06) |
| Q16 | Applicant details in Telegram | No: first name + channel + type only (2026-10-06) |

## Still open (deferred by owner on 2026-09-28; Q3/Q9/Q13 are needed by M5, Q4 by M7)

| ID | Question | Why it matters | Blocks |
|---|---|---|---|
| Q3 | Will "Support the Project" include donation links? Vercel Hobby is non-commercial only | Plan choice | M5 (copy only) |
| Q4 | Final domain (custom vs `*.vercel.app`). Default until decided: `*.vercel.app` | Canonical URLs, sitemap, redirect page | M7 |
| Q8 | Will anyone besides the owner use the admin in the next 6 months? | If yes, local token auth is insufficient | Architecture |
| Q9 | Privacy notice (KVKK) text and retention (proposed 12 months): who drafts and approves it? | Required before the form goes live | M5 |
| Q10 | Keep admin + API code in this public repo? (Recommended: yes, no secrets in code) | Repo split | M1 |
| Q11 | Does anyone consume `events.json` directly? | Keep a JSON endpoint on the new site? | M7 |
| Q12 | Category vocabulary for filters | Filters, later LLM labels | M2 |
| Q13 | Is there an existing WhatsApp community/group, or will it be created too? | Community page copy and manual invite process | M5 |
| INV-T1 | Telegram: 48 h delete rule for channel admins | Correction workflow | V1.1 |
| INV-C1..C4 | Devpost ToS, Eventbrite API status, DoraHacks ToS, Patika robots details | Discovery source list | V1.4 |
