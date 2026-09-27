# Local LLM Research

Checked 2026-09-27 against `docs.ollama.com`, `ollama.com/library`, Hugging Face model cards, and vendor announcements. **No models were downloaded during planning.**

## 1. Runtime: Ollama vs llama.cpp

| Criterion | Ollama | llama.cpp (llama-server) |
|---|---|---|
| RTX 5070 (Blackwell, CC 12.0) | Officially listed as supported; driver ≥ 550 (installed: 616.92) | Supported (CUDA build) |
| Structured output | `format` accepts a **JSON Schema** (Pydantic `model_json_schema()`); also OpenAI-compatible `response_format` | GBNF grammars / JSON schema |
| Model management | `ollama pull`, tags, automatic offload | Manual GGUF files |
| Windows | Native installer | Prebuilt binaries |
| Caveat | "Ollama's Cloud currently does not support structured outputs", which only matters if we use Ollama Cloud | More knobs, more setup |

**Decision:** Ollama for development and V1.x. llama.cpp is the fallback if we need fine control (e.g. a grammar feature Ollama lacks). Because Ollama exposes an OpenAI-compatible API, switching later only affects the provider class.

Pass 2: *"Is local AI necessary at all in V1?"* No. V1 only proves connectivity and one schema-constrained call. Extraction starts in V1.2. The local-first choice rests on cost (free), privacy of community data, and developer preference. Its risk is quality: small models make extraction mistakes. That is why deterministic validation + human review sit after the LLM.

## 1a. Installed runtime (verified 2026-09-28)

- Ollama **0.34.2** installed via winget, listening on **`127.0.0.1:11434` only**. `OLLAMA_HOST` is unset.
- Server log: `inference compute … library=CUDA compute=12.0 … RTX 5070 Laptop GPU … total="7.9 GiB" available="6.8 GiB"`.
- The integrated AMD Radeon 880M is ignored by default ("dropping integrated GPU"), which is what we want.
- **Practical VRAM budget is about 6.8 GiB, not 8 GB**, because the display and other apps hold the rest. This changes the fit assessment below.

## 2. Candidate models (fit for ~6.8 GiB usable VRAM)

Sizes are from Ollama tags pages. VRAM use is larger than file size because of the KV cache (context).

| Model tag | File size | Context | License | Notes |
|---|---|---|---|---|
| `qwen3.5:4b-q4_K_M` | 3.4 GB | 256K | Apache 2.0 | Fits fully in VRAM with a large context; thinking on by default (disable with `think: false`) |
| `qwen3.5:9b-q4_K_M` (`latest`) | 6.6 GB | 256K | Apache 2.0 | With 6.8 GiB available, it does **not** fully fit once the KV cache is added. Expect partial CPU offload and slower runs. Benchmark it anyway as the quality reference |
| `gemma4:e2b-it-qat` | 4.3 GB | 128K | Apache 2.0 (Gemma 4 moved to Apache 2.0, 2026-04) | Small, fast |
| `gemma4:e4b-it-qat` | 6.1 GB | 128K | Apache 2.0 | Tight fit on 6.8 GiB (small context only). The default `e4b` tag is 9.6 GB and does **not** fit |
| `qwen3:8b` | ~5 GB | — | Apache 2.0 | Older baseline for comparison |

Excluded: `gemma4:12b` (7.2–7.6 GB, which leaves no room for the KV cache on 8 GB), all ≥ 26B models, and cloud-only tags.

Turkish: the Qwen3.5 card claims 201 languages but does not list Turkish explicitly. Gemma is multilingual. **Turkish quality is unverified for all candidates and must be measured.**

## 3. Benchmark plan (run in V1.2, not during planning)

**Dataset:** 20 real event pages:
- the 6 URLs from the current `events.json` (a gold answer is partially available);
- 7 Devpost pages and 7 Turkish organizer or university pages.

For each page, the owner writes a gold JSON (title, organizer, start/end date, deadline, format, city, team min/max, official URL, application URL).

**Tasks per model:**
1. Structured extraction into the `EventExtraction` schema (temperature 0, `think: false`, `num_ctx` 8192 / 16384).
2. Turkish summary of at most 280 characters.
3. Telegram caption of at most 900 characters, in Turkish, from the structured data only.
4. Duplicate judgement on 10 prepared pairs (5 true duplicates, 5 near misses).

**Metrics:**

| Metric | How |
|---|---|
| Schema validity | % of outputs passing `model_validate_json` without retry |
| Field accuracy | Exact match for dates and URLs; normalized match for names |
| Hallucination | Fields filled when the page does not contain them (should be `null`) |
| Turkish quality | Owner rates 1–5, blind (model name hidden) |
| Speed | tokens/s and wall time per page |
| VRAM peak | `nvidia-smi --query-gpu=memory.used` sampled every 0.5 s |
| Duplicate accuracy | Correct / 10 |

**Pass criterion for the default model:** ≥ 95 % schema validity, 0 fabricated dates, date accuracy ≥ 90 %, Turkish ≥ 3.5/5, under 60 s per page.

**Download budget:** at most 4 models, about 20 GB in total. Remove the losers afterwards.

## 4. Rules that do not depend on the model

- The LLM never produces the final value of dates or URLs without evidence. Every extracted field must quote the source snippet it came from, and deterministic code checks that the snippet exists in the fetched text (see AI_ARCHITECTURE).
- Confidence percentages are not shown in the UI.
