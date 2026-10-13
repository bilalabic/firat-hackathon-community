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

## Resolved (2026-10-13, owner; decisions accepted as D-23 to D-26)

| ID | Question | Answer |
|---|---|---|
| — | LLM provider | OpenAI API, default `gpt-5.4-mini` pending the benchmark; Ollama stays as fallback (D-23). `web_search` is paid (not in the free tokens), so it is a gap-finder only |
| INV-C1 | Devpost ToS / permission | ToS §4 forbids automated access. Owner decided to integrate Devpost directly without asking for permission and accepts the risk (R-21); mitigations and `DEVPOST_ENABLED` kill switch in V1_4_DISCOVERY |
| INV-C2..C4 | Eventbrite API, DoraHacks ToS, Patika robots | Eventbrite: search API deprecated, disabled. DoraHacks: bot wall, manual only. Patika: `Allow: /` (DISCOVERY_RESEARCH §1) |
| — | Discovery engine | Source adapters + change detection first, then watchlists, admin-bot forwards + community suggestions, web_search 2×/week, one-hop links (D-24) |
| — | Geographic scope | All in-person events in Türkiye + online events (global included); no in-person abroad |
| — | Event types | Hackathon, ideathon, datathon (incl. Kaggle-style), game jam, Teknofest-style competition, all included; type field + public and admin filters (D-25) |
| — | Daily review budget | 10–15 drafts/day → relevance threshold + daily draft cap (default 15) |
| — | Scheduling | Windows Task Scheduler on the local machine with catch-up; no cloud runners (D-26) |
| Q18 | Gold list | Start now (4 weeks, target ≥ 30 events); the owner maintains it in the template `services/api/bench/discovery_gold.template.csv` (copied to the gitignored `bench/data/discovery_gold.csv`) |
| Q20 | Public route once other types are listed | `/etkinlikler` with the title "Etkinlikler"; `/hackathonlar` URLs redirect permanently (D-25, V1.3) |

## Still open (deferred by owner on 2026-09-28; Q3/Q9/Q13 are needed by M5, Q4 by M7)

| ID | Question | Why it matters | Blocks |
|---|---|---|---|
| Q3 | Will "Support the Project" include donation links? Vercel Hobby is non-commercial only | Plan choice | M5 (copy only) |
| Q4 | Domain: owner decided 2026-10-06 to keep `firat-hackathon-community.vercel.app` for now | — | resolved |
| Q8 | Will anyone besides the owner use the admin in the next 6 months? | If yes, local token auth is insufficient | Architecture |
| Q9 | KVKK notice: approved 2026-10-06 and live at `/aydinlatma-metni` (D-22; the transfer-basis risk is accepted by the owner, R-20) | — | resolved |
| Q10 | Keep admin + API code in this public repo? (Recommended: yes, no secrets in code) | Repo split | M1 |
| Q11 | Does anyone consume `events.json` directly? | Keep a JSON endpoint on the new site? | M7 |
| Q12 | Category (topic) vocabulary for filters. Event **types** are decided (D-25); topics (`ai`, `fintech`…) are still open | Filters, later LLM labels | V2 |
| Q13 | Is there an existing WhatsApp community/group, or will it be created too? | Community page copy and manual invite process | M5 |
| INV-T1 | Telegram: 48 h delete rule for channel admins | Correction workflow | V1.1 |
| Q17 | OpenAI org: which usage tier, and is data sharing enabled on the project that carries public page text? Do the complimentary-token caps (250k / 2.5M per day) cover `gpt-5.4-mini` / `gpt-5.4` on the Responses API for our org? | Token budget and whether extraction is free; KVKK (data sharing only for public pages, R-22) | V1.2 OpenAI benchmark |
| Q19 | Which Telegram / WhatsApp / Instagram / LinkedIn channels do admins follow (sources for forward-to-bot)? | Inbound coverage, watchlist seeds | V1.4b |
