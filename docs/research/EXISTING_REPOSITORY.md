# Existing Repository Analysis

Inspected: 2026-09-27, commit `6b0306a` (branch `main`, clean working tree).

## 1. Inventory

The repository is small: 10 tracked files, 8 commits, ~1,500 lines.

| Path | Purpose | Lines |
|---|---|---|
| `index.html` | Single static page (Turkish UI) | 84 |
| `style.css` | Mobile-first styles, light + automatic dark theme | 500 |
| `script.js` | Vanilla JS: fetch `events.json`, compute status, sort, search, filter | 324 |
| `events.json` | The only data store (6 events) | 74 |
| `.github/ISSUE_TEMPLATE/event.yml` | Issue Form "Etkinlik Ekle" (add event) | 89 |
| `.github/ISSUE_TEMPLATE/config.yml` | Disables blank issues, mailto contact link | 5 |
| `.github/scripts/add_event.py` | Parses Issue Form body, validates, appends to `events.json` | 248 |
| `.github/workflows/add-event.yml` | Issue opened → validate → commit → deploy → close issue | 106 |
| `.github/workflows/deploy-pages.yml` | GitHub Pages deploy (push to `main`, dispatch, `workflow_call`) | 44 |
| `README.md` | Turkish README | 72 |

There is **no** `package.json`, lockfile, Python project file, `.gitignore`, `.env*`, tests, linters, or build step.

## 2. How it works today

```text
Owner opens Issue (label "etkinlik")
  → add-event.yml (only if author == repo owner AND label present)
  → add_event.py validates form, dedupes by normalized URL, writes events.json
  → commit + push by github-actions[bot]
  → deploy-pages.yml called via workflow_call (GITHUB_TOKEN pushes do not trigger workflows)
  → issue commented + closed
Browser loads index.html → fetch("./events.json") → status computed client-side
```

Verified against GitHub (via `gh`):

- Repository is **public**; default workflow permissions are `read`.
- Pages `build_type: workflow`, HTTPS enforced, live at `https://bilalabic.github.io/firat-hackathon-community/` (HTTP 200, serves current `events.json`).
- Issues #1–#5 were test issues; runs show success, validation failure (#2, #3) and skip (#4, unlabeled) paths all worked as designed.
- No PRs, no remaining branches besides `main` (an earlier Copilot branch no longer exists), no Actions secrets or variables.
- Label `etkinlik` exists.

## 3. Observations

### Data model (`events.json`)
Fields: `id, name, organizer, deadline, eventDate, location, format, teamSize, description, url`.

Problems found:

1. **No end date.** `eventDate` is the start date only. Multi-day events (e.g. Greece–Türkiye: semifinal Nov 26–27, final Dec 3–4) are shown as "ended" the day after the start date.
2. **Location and format are mixed.** `location: "Online"` duplicates `format: "Online"`; `"Online / Santa Clara, ABD"` merges two locations into free text.
3. **Team size is free text** (`"1-4 kişi"`, `"Belirtilmemiş"`) — cannot be filtered.
4. **No provenance** — one `url`, no distinction between official page and registration page; no "last verified" timestamp.
5. **No lifecycle** — every entry in the file is public; no draft/review state.
6. **Stale data.** As of 2026-09-27, 3 of 6 events are past, and the file was last changed on 2026-08-17. This is evidence that the manual Issue Form loop is the real bottleneck, which supports prioritising assisted import (see ROADMAP).

### Frontend
- Good: semantic HTML, skip link, `aria-pressed` chips, `aria-live` result count, `prefers-reduced-motion`, dark theme, DOM built with `textContent` (no `innerHTML`), URL scheme allow-list (`safeUrl`).
- Status logic (`open` if today ≤ deadline, `upcoming` if today ≤ eventDate, else `ended`) is simple and correct for single-day events; the "last 3 days" countdown is a good UX idea.
- Turkish-aware search normalization (`ı→i`, `ş→s`…) is a useful detail to keep.
- Limitations: one page, no detail pages, no per-event SEO/OpenGraph, no sitemap, contact is a `mailto:` link.

### Automation
- `add_event.py` is carefully written: never builds JSON by string concatenation, validates before and after writing, passes untrusted issue body via env var (not shell interpolation), writes multi-line outputs with heredoc delimiters.
- `add-event.yml` follows least privilege (`contents: read` default, per-job grants) and restricts processing to the owner.
- `deploy-pages.yml` uploads **`path: .`** — the entire repository becomes the Pages artifact.

## 4. Classification

| Part | Class | Reason |
|---|---|---|
| Event records in `events.json` (6 items) | **KEEP** (migrate) | Real curated content; import into the new DB as the seed. |
| Status semantics (open / upcoming / ended computed from dates, never stored) | **KEEP** | Correct principle; extend with `end_date` and "closing soon". |
| Turkish search normalization, URL scheme allow-list, `textContent`-only rendering | **KEEP** (port) | Port the ideas to the Python normalizer and the Next.js app. |
| Accessibility patterns (skip link, aria attributes, reduced motion) | **KEEP** (port) | Reapply in the new public site. |
| `events.json` as the source of truth | **REPLACE** | Cannot model lifecycle, provenance, or publication history; public site and admin need a shared DB. |
| `index.html`, `style.css`, `script.js` | **REPLACE** (after cutover) | Replaced by the Next.js public site. Keep serving until the Vercel site reaches parity. |
| Issue Form + `add_event.py` + `add-event.yml` | **REPLACE** (after cutover) | Local admin replaces this intake. Keep working until cutover so the site can still be updated. |
| `deploy-pages.yml` | **REFACTOR now, REMOVE at cutover** | Must stop uploading the whole repo (see Security S2) before any new code is added; later replaced by a redirect page. |
| `.github/ISSUE_TEMPLATE/config.yml` | **REFACTOR** at cutover | Contact link should point to the new Community page. |
| `README.md` | **REFACTOR** | Rewrite in English for the monorepo (milestone M7). |
| Missing `.gitignore`, `.env.example` | **ADD** (M0) | Required before any secrets exist locally. |
| Nothing | **REMOVE now** | No dead code was found. Removal only happens at cutover. |
| Pages URL after migration | **INVESTIGATE** | GitHub Pages cannot do server redirects; a meta-refresh page is the likely answer. Depends on the final domain. |

## 5. Verification record

| Conclusion | Check 1 | Check 2 |
|---|---|---|
| `deploy-pages` needs `workflow_call` | `add-event.yml` calls it after pushing with `GITHUB_TOKEN` | Run history: issue #5 run (21:20) has no separate push-triggered deploy, confirming GITHUB_TOKEN pushes do not trigger workflows |
| Nothing else depends on `events.json` | `grep` across repo: only `script.js`, `add_event.py`, workflow | Pages serves it directly; no external consumer known (open question: anyone embedding the JSON?) |
| No secrets in history | Pattern scan of `git log --all -p` (keys, tokens, private keys) → only `id-token: write` matches | No Actions secrets configured (`gh secret list` empty). Note: this is a pattern scan, not a full `gitleaks` scan. |
| Static site can be removed at cutover | Only referenced by Pages workflow | Live site URL is referenced in README and issue comments only |
