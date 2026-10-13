# LLM Extraction Benchmark (V1.2)

Status: **done 2026-10-13**; default model `gpt-5.4-mini` (D-23). Gold answers still need the owner check; Turkish summary rating pending.
Plan and pass criteria: `LOCAL_LLM_RESEARCH.md` §2-3. Prepared 2026-10-11.

## Method

- **Input:** 20 real public hackathon pages, fetched **once** with the repo's `SafeFetcher`
  (`bench/fetch_pages.py`): robots.txt checked per host (none of the pages was disallowed), at least 2.5 s
  between any two requests, `USER_AGENT` of the repo. Raw HTML is stored in
  `services/api/bench/data/pages/` (gitignored; third-party content). The run replays the saved HTML,
  so nothing is fetched again.
- **Gold answers:** `bench/data/gold/<id>.json` (gitignored), drafted by the agent from the page text, one entry
  per `ExtractableField` with the supporting snippet (each snippet was checked to occur in the saved page).
  `null` = the page does not state it. Fields where the page is contradictory or ambiguous carry
  `"ambiguous": true` and are not scored. Every file has `"needs_owner_check": true`: **the owner must review
  the gold before the numbers are trusted.** `summary` and `eligibility` are rated by hand, not string-compared.
- **Pipeline under test:** loader -> `LLMExtractor` with `OllamaProvider` (temperature 0, `think: false`,
  schema-constrained), once per model and page, sequentially.
- **Metrics** (`bench/scoring.py`, unit-tested in `tests/test_bench_scoring.py`):

| Metric | Definition |
|---|---|
| Schema validity | extraction finished without `llm_error` (the provider's one repair retry is included; first-try validity is not exposed by the extractor) |
| Field accuracy | correct / (correct + wrong + missed) over fields with a gold value. Exact for dates (ISO), numbers, booleans, codes; URLs normalized (host case, fragment, trailing slash); text normalized (NFKC, case, Turkish i, punctuation) with containment |
| Hallucination | field filled although gold is null (and not ambiguous); fabricated dates counted separately |
| Wall time | loader + extractor per page; p50 / p95 / max; the first page includes the model load (cold start) |
| VRAM peak | `nvidia-smi --query-gpu=memory.used` every 0.5 s during the model's run, baseline recorded before |
| Turkish quality | owner rates the `summary` of each page 1-5, blind (`rating-sheet`: letters A-D, shuffled per page, key in a separate file) |

Pass criteria for the default model: schema validity >= 95 %, 0 fabricated dates, date accuracy >= 90 %,
Turkish >= 3.5/5, < 60 s per page.

### Usage

```powershell
cd services\api
uv run python bench\fetch_pages.py                       # only to re-create the snapshots
uv run python bench\extraction_bench.py run --models qwen3.5:4b-q4_K_M gemma4:e2b-it-qat gemma4:e4b-it-qat qwen3.5:0.8b
uv run python bench\extraction_bench.py rating-sheet bench\data\results\<run>.json
```

`run` writes `bench/data/results/<run>.json` and `.md`. The loader/extractor classes are created in
`make_pipeline` (two marked lines); they are imported lazily because the modules did not exist when the
harness was written. `--loader builtin` swaps in a tiny stdlib HTML-to-text loader for early tests.
Known limitation: tokens/s is not reported (the extractor exposes only `llm_duration_ms`).

## Models

Tags were checked on `ollama.com/library/qwen3.5/tags` and `.../gemma4/tags` on 2026-10-11; all
candidates from LOCAL_LLM_RESEARCH §2 still exist under the same names. Pulled with Ollama 0.40.1; digests
match the tags pages.

| Tag | Size | Digest (short) | Role |
|---|---|---|---|
| `qwen3.5:4b-q4_K_M` | 3.3 GB | `d8b0f5e9760c` | main small candidate, fits fully |
| `gemma4:e2b-it-qat` | 4.3 GB | `07ea59a47401` | small, fast; Gemma family for Turkish |
| `gemma4:e4b-it-qat` | 6.1 GB | `ee6656371218` | larger Gemma, tight on ~6.8 GiB VRAM (watch the KV cache) |
| `qwen3.5:0.8b` | 1.0 GB | `34227f3be981` | already installed; lower bound |

Total new downloads: 13.7 GB (limit 20 GB). `qwen3.5:9b-q4_K_M` (6.6 GB) was **not** pulled: it does not fit in
6.8 GiB with a useful context, would run partly on CPU, and the 3-pull limit was used on better fits. Add it
later only if all three small models fail the criteria. Remove the losers afterwards (`ollama rm`).

## Dataset

"JSON-LD" = a schema.org `Event` block is present in the HTML (the structured values should win over the LLM).
Ids are the file names in `bench/data/pages/`.

| Id | URL | Lang | JSON-LD Event |
|---|---|---|---|
| legacy-grid-up | https://www.patika.dev/bootcamp/grid-up-hackathon | tr | no |
| legacy-zemin360 | https://www.zemin360.com/hackathon | tr | yes |
| legacy-borsa-istanbul | https://www.borsaistanbul.com/fintech-hackathon | tr | no |
| legacy-greece-turkiye | https://greeceturkiyehackathon.com | en | no |
| legacy-devnetwork-api | https://api-cloud-ai-hackathon-2026.devpost.com/ | en | yes |
| legacy-oneaquahealth | https://oneaquahealth-ieee-hackathon.devpost.com/ | en | yes |
| devpost-hackturin | https://hackturin-2026.devpost.com/ | it/en | yes |
| devpost-codered-orion | https://codered-orion-ccs.devpost.com/ | en | yes |
| devpost-hacknc | https://hacknc-2026.devpost.com/ | en | yes |
| devpost-paypal-ai | https://paypalaihackathon.devpost.com/ | en | yes |
| devpost-qloo | https://qloo.devpost.com/ | en | yes |
| devpost-next-byte | https://next-byte-hacks-v5.devpost.com/ | en | yes |
| devpost-indux | https://indux-5-0-2026.devpost.com/ | en | yes |
| tr-vbt-mugla | https://nuriokumus.github.io/Hackathon2026/ | tr | no |
| tr-datamedx | https://aday.istinye.edu.tr/datamedx-hackathon | tr | no (WebPage graph only) |
| tr-anadolu-ozal | https://www.ozal.edu.tr/page/announcement/anadolu-hackathon-yarismasi-basvurulari-basliyor-1536 | tr | no |
| tr-anadolu-ankara | https://sw.eng.ankara.edu.tr/2026/03/17/anadolu-hackathon-etkinligi-hk/ | tr | no |
| tr-ytu-student | https://www.yildizteknopark.com.tr/duyurular/student-hackathon-egitim-serisi-basvurulari-acildi.html | tr | no |
| tr-ing-orkam | https://orkam.yildiz.edu.tr/ing-hubs-turkiye-agentic-ai-hackathon-basvurulari-basladi/ | tr | no |
| tr-ing-coderspace | https://coderspace.io/etkinlikler/ing-hubs-turkiye-agentic-hackathon | tr | yes |

Notes for interpreting results:

- Several pages changed since `events.json` was written (dates, deadlines); the gold follows the page, not `events.json`.
- Many events are already over (the pages are real, not curated for the future); this does not affect extraction.
- `tr-anadolu-ozal` and `tr-anadolu-ankara` announce the same event with different dates (a deliberate conflict case).
- Devpost "Deadline" is the submission deadline, so `application_deadline` is not scored there.
- Devpost start dates exist only in JSON-LD (the main text shows the end only); the LLM sees text, so a missing
  start there reflects the loader/merge design, not model quality.
- Rejected candidates: `btkakademi.gov.tr/.../ankaraaihackathon26` (JavaScript-only, no readable content; confirms the
  "no Playwright in V1.2" decision) and `ktu.edu.tr/.../anadolu-hackathon-yarismasi` (third page of the same event).
- Gold gaps: `application_url` is only filled where an explicit apply link exists in the HTML; the LLM sees main text,
  so structured/link extraction by the loader is the realistic source for it.

## Results

All runs use the real loader (`--loader real`) on the saved pages. Gold answers are marked
`needs_owner_check`, so the numbers are provisional.

### Run 1: local models, before the error-analysis fixes (2026-10-11, 20 pages)

| Model | Valid | Acc. | Date acc. | Halluc. | Fab. dates | p50 s | max s | VRAM MiB |
|---|---|---|---|---|---|---|---|---|
| `qwen3.5:0.8b` | 100% | 58% | 59% | 20 | 1 | 5.6 | 13.6 | 1588 |
| `qwen3.5:4b-q4_K_M` | 100% | 66% | 73% | 8 | 1 | 9.5 | 13.6 | 5847 |
| `gemma4:e2b-it-qat` | 100% | 66% | 70% | 17 | 2 | 6.9 | 53.3 | 5847 |
| `gemma4:e4b-it-qat` | 100% | 68% | 73% | 4 | 0 | 11.4 | 21.7 | 4458 |

The error analysis (commit 24bef21) found most losses in the loader (sidebars and links missing
from the text) and in false rejections by the evidence checks, not in the models. After the fixes a
5-page check with `gemma4:e4b-it-qat` gave 71% → 88% accuracy and 71% → 100% date accuracy.

### Run 2: OpenAI, after the fixes (2026-10-13)

Mini models on all 20 pages; full models on 8 pages (to stay inside the 250k/day full-model pool):
`legacy-borsa-istanbul legacy-greece-turkiye devpost-hackturin devpost-indux tr-vbt-mugla
tr-ing-coderspace tr-datamedx tr-anadolu-ankara`.

| Model | Pages | Valid | Acc. | Date acc. | Halluc. | Fab. dates | p50 s | max s | Tokens in / out per page |
|---|---|---|---|---|---|---|---|---|---|
| `gpt-5.4-mini` | 20 | 100% | 92% | 100% | 3 | 0 | 3.6 | 5.4 | 3379 / 540 |
| `gpt-4.1-mini` | 20 | 100% | 92% | 100% | 4 | 1 | 4.3 | 6.9 | 3381 / 592 |
| `gpt-5.4` | 8 | 100% | 92% | 100% | 0 | 0 | 6.8 | 8.9 | 3216 / 572 |
| `gpt-4o` | 8 | 100% | 92% | 100% | 1 | 0 | 3.9 | 5.1 | 3219 / 528 |

Per-field accuracy (20 pages, mini models): title 100/100, organizer 81/75, format 86/86, city
83/83, country 80/40, venue 80/80, start/end/deadline 100, team_min 91/91, team_max 100,
prize_pool 100, currency 92/92, is_free 100/100, application_url 75/100 (`gpt-5.4-mini` /
`gpt-4.1-mini`). Weakest fields in every model: country, city, venue, organizer; part of this is
likely gold error (seven suspected gold errors are listed for the owner).

### Decision

- **Default: `gpt-5.4-mini`** (reasoning effort `none`, temperature 0). Same accuracy as the full
  models, no fabricated dates, fastest, and in the 2.5M/day pool: about 3.9k tokens per page, so
  roughly 600+ pages per day.
- `gpt-4.1-mini` is not chosen: one fabricated date and weak `country`.
- `gpt-5.4` stays the ceiling for retries and flagged cases (D-24), not the default.
- Ollama (`gemma4:e4b-it-qat`) stays as the offline fallback (`LLM_PROVIDER=ollama`).
- Pass criteria (LOCAL_LLM_RESEARCH §3): validity ≥ 95% ✓, 0 fabricated dates ✓, date accuracy
  ≥ 90% ✓, < 60 s per page ✓, Turkish quality ≥ 3.5/5: **pending the owner's blind rating**.
- Local models no longer needed can be removed by the owner (`ollama rm qwen3.5:0.8b
  qwen3.5:4b-q4_K_M gemma4:e2b-it-qat`); keep `gemma4:e4b-it-qat` as the fallback.
