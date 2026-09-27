# Crawling and Discovery Research

Checked 2026-09-27. This document informs V1.2–V1.4. **No crawler is built in V1.**

## 1. Retrieval tools

| Tool | Status (verified) | Role |
|---|---|---|
| `httpx` | Mature | All HTTP retrieval, with timeouts, size caps and redirect limits |
| `selectolax` 0.4.12 (2026-09-18) | MIT (Lexbor engine Apache-2.0), Windows wheels, Python 3.9–3.14 | Fast parsing: `<script type="application/ld+json">`, `<meta>`, links |
| `trafilatura` 2.2.0 (2026-07-31) | Apache 2.0 (since 1.8), Python ≥ 3.10, Markdown output + metadata | Main-content text for LLM input |
| Playwright (Python) | Mature | Fallback for JS-rendered pages only, enabled per source |
| Crawl4AI 0.9.x | Browser-first (installs Playwright browsers via `crawl4ai-setup`), "undetected" modes | **Not used.** It adds nothing over the tools above, and stealth modes conflict with our "respect the source" rule |
| `feedparser` | Mature | Only if a source offers RSS/Atom |

### Retrieval order (revised)

The proposed order was `HTTP → Crawl4AI → Playwright`. **Revised:**

```text
1. Official API / JSON endpoint / RSS (if the source has one)
2. httpx GET → selectolax: JSON-LD schema.org/Event + OpenGraph + <meta>
3. trafilatura main text (for LLM extraction)
4. Playwright render → steps 2–3 again   (only if source.requires_js = true)
```

Reason: step 2 alone often gives structured dates, location and URLs. Many event platforms embed `schema.org/Event` JSON-LD for SEO. That data is deterministic and needs no LLM. Crawl4AI would sit between 3 and 4 and duplicate both.

## 2. Source hierarchy

| Tier | Meaning | Can verify? |
|---|---|---|
| 1 | Official organizer or event website | Yes: facts are confirmed here |
| 2 | Trusted event platform page for that specific event (Devpost, DoraHacks, ETHGlobal, Luma, Eventbrite) | Yes, if the organizer runs the event on the platform |
| 3 | Official social announcement (organizer's account) | Partially: dates must be confirmed on Tier 1/2 |
| 4 | Secondary: aggregators, newsletters, blogs, community reposts | No: discovery only |

Rule: an event may reach `verified` only when the dates, deadline and application URL are each backed by a Tier 1 or 2 source.

## 3. Source-by-source findings

| Source | Official API | robots.txt (fetched 2026-09-27) | Rendering | Assessment |
|---|---|---|---|---|
| Devpost | No documented public API. `GET https://devpost.com/api/hackathons?status[]=upcoming` returns JSON (HTTP 200, verified) but is **undocumented** | `User-agent: *` with empty `Disallow` (allowed); specific bots blocked | Server-rendered pages | Tier 2. Good first discovery source. Treat the endpoint as unstable: parse defensively, fail closed, and cache. Terms of Service review required before automation (**INVESTIGATE C-1**) |
| Luma | API requires **Luma Plus**, and keys are **scoped to one calendar** (own calendar only) | Only a few paths disallowed (`/social-share`, `/in/`, `/company/`, `/session-*`) | Pages embed data | API is not usable for discovery. Individual public event pages can be read as Tier 2 when linked from elsewhere |
| Eventbrite | Public event *search* API reportedly deprecated years ago (**not re-verified**, INVESTIGATE C-2) | Disallows `/rss/`, `/atom/`, calendar/query variants | Server-rendered | Low value for hackathons in Türkiye. Postpone |
| DoraHacks | None found | `/robots.txt` returns the SPA HTML (no robots file) | JS-rendered SPA | Would need Playwright. Postpone; review ToS (C-3) |
| ETHGlobal | None found | `/robots.txt` returns app HTML (no robots file) | Next.js app | Event list is small and curated. Consider a manual watch list |
| Patika.dev (in current data) | None | `User-Agent: *` present; no restrictive rules seen in the first lines (C-4) | — | Important Turkish source (Grid Up Hackathon). Check individual pages |
| Universities, Turkish foundations, company pages | Rarely | Varies | Mostly static | Tier 1 when official. Best handled as a curated `sources` list, not broad crawling |
| GitHub | REST API (official) | — | — | Useful later for organizer repos. Low priority |

Missing robots.txt ≠ permission. Our policy: honor robots.txt where present, identify with a descriptive User-Agent that includes a contact URL, rate-limit to 1 request / 5 s per host, never bypass logins or bot protection, and prefer official feeds.

## 4. Discovery strategy (recommendation)

1. **V1.2: URL import.** The admin pastes a URL, and the system fetches, extracts and creates a draft. This removes the current bottleneck (manual form filling) without any crawling policy risk.
2. **V1.4: curated sources.** A `sources` table with about 10–30 hand-picked Tier 1/2 feeds (Devpost JSON, specific organizer pages). Each has a retrieval method and a check interval.
3. **Later: search-based discovery.** Requires a search API (cost/terms not yet evaluated).

## 5. Security requirements for any fetcher (apply from V1.2)

- **SSRF:** resolve DNS, reject private, loopback, link-local and metadata ranges (`127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254/16`, `::1`, `fc00::/7`, `fe80::/10`). Re-check after each redirect. Allow only `http`/`https` on ports 80 and 443. Allow at most 5 redirects.
- **Resource limits:** 10 s connect/read timeout, 5 MB body cap (streamed), only HTML, JSON, XML and image content types.
- **Images:** download only when the admin selects them. Verify magic bytes, cap at 5 MB, re-encode through Pillow (strips metadata and payloads), never serve the original bytes.
- **Content is data:** fetched text goes to the LLM only inside the untrusted-data envelope (see SECURITY.md §5).
- **Playwright:** no persistent profile, downloads disabled, run as the normal user, one page per context, closed after use.
