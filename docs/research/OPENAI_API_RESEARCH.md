# OpenAI API research (Ollama → OpenAI)

Status: research only, 2026-10-13. All sources accessed 2026-10-13. Pages under
`platform.openai.com/docs/*` now 301-redirect to `developers.openai.com/api/docs/*`.
**[UNVERIFIED]** marks claims that no official page we could read confirms. The data-sharing help
article returned HTTP 403 to WebFetch, curl and the browser tool, so its terms come from search
snippets of it and from community posts.

## 1. Data-sharing program ("share traffic with OpenAI")

**What is shared.** By default, API data "is not used to train or improve OpenAI models … unless
you explicitly opt in to share data with us" [S1]. Opting in means the org's (or the project's,
see below) prompts and completions **may be used to train and improve models**. Abuse-monitoring
logs are kept up to 30 days in any case. `/v1/responses` with `store` true or omitted keeps
response data "for at least 30 days" [S1].

**Complimentary tokens.** The owner's limits (250k/day large group, 2.5M/day small group) match
the published Usage Tier 1–2 limits. Higher tiers get 1M and 10M [S2, S3]. The rate-limit guide
now names its tiers Free/Build/Launch/Grow [S11]. How these map to "Tier 1–2" is **[UNVERIFIED]**.
- Daily reset at 00:00 UTC [S3, community]. The two groups are separate pools.
- Excluded: "Fine-tuned models, fine-tuning, evals, and tool use" [S2, snippet of the help
  article]. So **`web_search` is not covered.** We have to assume both the $10/1k calls and the
  search-content tokens are billed.
- Above the cap: billed at standard rates [S3 secondary; **UNVERIFIED** first-hand]. A positive
  credit balance is required even for free usage [S2].
- Cached input: not stated whether it counts against the pool or at what rate. **[UNVERIFIED]**
- Responses API coverage: a 2025 forum reply said Chat Completions and Batch only. A 2026 user
  saw `"billing": {"payer": "openai"}` on Responses [S4]. **[UNVERIFIED]**. Test it (see §5).
- Known billing bugs: free tokens were sometimes charged, and gpt-5.4-mini was once counted
  against the wrong pool [S4]. OpenAI gives 30 days' notice before it ends the program [S2].
- Scope: the setting can be org- or project-level [S3 secondary, **UNVERIFIED**].

**Capping spend.** In Project settings → Limits → Spend, set a **Monthly spend limit** and turn on
**Enforce a hard limit**. Above it, requests get `429 project_spend_limit_exceeded`. Enforcement is
not instantaneous, so small overshoots are possible. The limit resets monthly [S5]. Alerts only
notify. Recommendation: a dedicated project "fhc-api" with data sharing enabled, a hard limit
(e.g. $5/month), a 50% alert, and its own key. Also track daily tokens in our own code from
`usage` and stop below 250k/2.5M. The free pool is not observable through the API, so this
counter is our only real guard.

**KVKK implications (D-22).** Anything we send under data sharing may be used for training, and
it is a cross-border transfer to the US. The aydınlatma metni does not list OpenAI as a recipient.
- **Never send:** `community_applications` / `team_applications` rows, names, emails, phones,
  student numbers, Telegram ids, free-text answers, admin notes, or anything derived from them.
- **Public pages also contain personal data** (organizer emails and phones, jury names).
  Extraction does not need email addresses or phone numbers, so redact them before sending.
- **Guard (recommended, enforced in code, not only by convention):**
  1. `OpenAIProvider` runs every outbound `system`+`user` string through a `PIIGuard` *before*
     the HTTP call. It redacts email addresses, TR/E.164 phone numbers and 11-digit numbers that
     pass the TC Kimlik checksum, each to a placeholder (`[email]`, …). It blocks with
     `LLMConfigError` if the text contains a marker of application data. Run unit tests on the
     guard.
  2. Callers in the applications domain cannot import the LLM provider. Add an architecture test
     (an import-linter style check in pytest).
  3. Send `store: false`. Send no `safety_identifier`/`metadata` with personal data. If we need
     one, use a hash of the admin id [S12].
  4. Add OpenAI to the privacy notice only if application data ever has to go there. The default
     answer is: never.

## 2. API choice and Structured Outputs

**Use the Responses API (`POST https://api.openai.com/v1/responses`).** OpenAI says "Responses is
recommended for all new projects". Chat Completions is still supported [S6]. Hosted tools
(`web_search`) exist only in Responses. Chat Completions has only search *models*, and the
gpt-4o search previews shut down on 2026-07-23 [S6, S7]. Responses stores by default, so always
send `store: false`. The `output_text` convenience is SDK-only. Over REST we parse `output[]` [S6].

**Structured Outputs** [S8]: `text.format = {type: "json_schema", name, schema, strict: true}`
(Responses). In Chat Completions the same goes in `response_format: {type: "json_schema",
json_schema: {...}}`. Rules:
- The root is an object and is not `anyOf`. **Every property is listed in `required`.** Optional
  fields are unions with `null`. **`additionalProperties: false` on every object.**
- Supported: string, number, boolean, integer, object, array, enum, anyOf. `$defs` + `$ref` and
  recursion are supported.
- Keywords: strings `pattern`, `format` (date-time, time, date, duration, email, hostname, ipv4,
  ipv6, uuid). Numbers `multipleOf`, `minimum`, `maximum`, `exclusiveMinimum/Maximum`. Arrays
  `minItems`, `maxItems`.
- Unsupported: `allOf`, `not`, `if/then/else`, `dependentRequired`, `dependentSchemas`.
- **`minLength`/`maxLength`** appear only on the "additionally unsupported for fine-tuned models"
  list. The supported-keywords list does not mention them. **Verified live 2026-10-13:**
  gpt-5.4-mini (effort `none`) and gpt-4o accept a strict schema with `maxLength` and `minimum`
  and return correct output.
- Limits: 5,000 properties, 10 nesting levels, 120k chars of names/enums, 1,000 enum values. An
  unsupported schema with `strict: true` → **error**. The first request with a new schema has
  extra latency.
- Refusals arrive as a content item `{"type": "refusal"}`. A cut-off response has `status:
  "incomplete"` and `incomplete_details.reason: "max_output_tokens"` [S8].

**Adapting our schemas.**
- `ExtractionOutput.model_json_schema()` produces `$defs`/`$ref` (OK) and `anyOf [{string,
  maxLength}, {null}]` for `str | None` (OK in nested positions).
- All our fields have no default, so they are already required. Pydantic does **not** emit
  `additionalProperties: false` unless `extra="forbid"` is set.
- Write a small `to_strict_schema(model)` in `llm/` that walks the schema, sets
  `additionalProperties: false` and `required = all keys` on each object, and strips
  `default` (and `title` noise). Keep `maxLength`/`minimum`/`maximum` (verified live
  2026-10-13).
- This is safe because extraction.py re-validates every field and the cap afterwards. Keep the
  Pydantic validation and the single repair retry. Strict mode makes it rarely needed, but
  refusals, truncation and our own field rules still happen.
- Use `format: "date"` for date fields instead of `description` (supported).

**Reasoning params.**
- gpt-5.4 and gpt-5.4-mini: `reasoning.effort` ∈ none (default), low, medium, high, xhigh
  [S9, S10]. Reasoning tokens are billed as output and reported in
  `usage.output_tokens_details.reasoning_tokens`. `max_output_tokens` includes them. OpenAI
  suggests reserving ≥25k when you experiment [S13].
- `temperature`/`top_p`: the current docs say "When reasoning effort is not `none`, remove
  `temperature`, `top_p`" (in the GPT-6 migration section) [S14]. **Verified live 2026-10-13:**
  gpt-5.4-mini at effort `none` accepts `temperature: 0`; gpt-4o accepts `temperature: 0`. The
  provider sends `temperature` to non-reasoning models and to reasoning models at effort `none`,
  and omits it at any other effort. gpt-4o and gpt-4.1-mini have no reasoning, so they get no
  `reasoning` param [S15, S16].

**Timeouts, retries, errors** [S11, S17].
- Headers: `x-ratelimit-{limit,remaining,reset}-{requests,tokens}`, the `-project-tokens`
  variants, and `Retry-After`. Failed requests count toward the per-minute limits.
- Retry with exponential backoff and jitter, honouring `Retry-After`, on: connection errors,
  timeouts, 429 rate-limit and `slow_down`, 500, 503 `server_is_overloaded`. The SDK's default is
  2 retries; it also retries 408 and 409 [S18].
- **Do not retry:** 429 `insufficient_quota` (check `error.code`, e.g. `credit_balance_exhausted`),
  429 `project_spend_limit_exceeded`, 400, 401 (key, org or IP allowlist), and 403 (unsupported
  region).
- Timeout: the SDK default is 10 min. Use ~60–120 s for us.
- Error body: `error.{message,type,param,code}`. `message` is documented only implicitly.

## 3. Built-in `web_search` tool (Responses)

[S7, S19]
- `tools: [{"type": "web_search"}]`. `web_search_preview` is legacy: it has no `filters` and no
  `return_token_budget`, and it ignores `external_web_access`.
- Models: listed for gpt-4.1, gpt-4.1-mini and o4-mini (128k search-context cap), and recommended
  on gpt-5.5. The model pages list it for gpt-5.4, gpt-5.4-mini and gpt-4o. It does **not** work
  with gpt-5 at `minimal` effort.
- Controls:
  - `filters.allowed_domains` / `blocked_domains`: up to 100 entries, subdomains included.
  - `user_location` (`country` ISO-2, city, region, timezone): for us, `TR`.
  - `search_context_size`: low, medium or high.
  - `external_web_access: false`: cache-only mode.
  - `tool_choice: "auto"`: searching is optional.
- Citations: `url_citation` annotations on `output_text` with `start_index`, `end_index`, `url`
  and `title`. `include: ["web_search_call.action.sources"]` returns every URL consulted.
- Pricing: **$10 per 1k calls + search content tokens at model rates**. For gpt-4o-mini and
  gpt-4.1-mini, the content is billed as a fixed 8,000 input tokens per call. The preview tool on
  non-reasoning models is $25/1k with free content tokens [S19].
- **Not covered by the complimentary tokens** (tool use is excluded) [S2].
- Implication for discovery (V1.4):
  - Cheapest option: our own search (a search API or a curated list of sites) plus our fetcher,
    then free-pool LLM calls for relevance and extraction.
  - With `web_search` on gpt-5.4-mini, 100 searches/day ≈ $1 in calls plus content tokens. That
    is affordable, but only under a hard spend limit.
  - Treat search results as untrusted content (§6). Code re-fetches and re-validates each
    candidate URL through the existing import pipeline.

## 4. Model recommendation and budget

**Token estimate per extraction page** (measured with `tiktoken` o200k_base on our code):
- System prompt: 821 tokens. Schema JSON: 1,481 tokens (whether the schema is billed as input is
  **[UNVERIFIED]**).
- Turkish text runs ≈ 3.5 chars/token, so 24k chars ≈ 6.9k tokens.
- Output is 17 `{value, snippet}` pairs, ≈ 0.7–1.2k tokens.
- **Total ≈ 9–10k tokens/page.** A repair retry roughly doubles it. Budget 12k on average.

| Pool | Models (examples) | Pages/day @12k | Price if billed (in/out per 1M) [S19] |
|---|---|---|---|
| 250k large | gpt-5.4, gpt-4o, gpt-4.1 | ~20 | 5.4 $2.50/$15 · 4o $2.50/$10 · 4.1 $2.00/$8 |
| 2.5M small | gpt-5.4-mini, gpt-4.1-mini, gpt-5-mini | ~200 | 5.4-mini $0.75/$4.50 · 4.1-mini $0.40/$1.60 |

**Lifecycle (deprecations page [S20]).**
- Shutting down **2026-10-23**: `o1`, `o3-mini`, `o4-mini`, `gpt-4.1-nano`, `gpt-4o-2024-05-13`.
- Snapshots `gpt-5`, `gpt-5-mini`, `gpt-5-nano` and `o3` shut down 2026-12-11.
- `gpt-5.1` and `gpt-5.4-nano` shut down 2027-04-01.
- No announcement for `gpt-4o` (the alias), `gpt-4.1`, `gpt-4.1-mini`, `gpt-5.4` or
  `gpt-5.4-mini`.
- So those models from the owner's free list are not viable for us.

**Comparison.** These are official claims only. Our own `LLM_BENCHMARK.md` run decides.

| Model | Context / max out | Cutoff | Reasoning | Official claim |
|---|---|---|---|---|
| gpt-4o | 128k / 16,384 | 2023-10 | no | "most capable model outside o-series" (old page wording) [S15] |
| gpt-4.1-mini | ~1.05M / 32,768 | 2024-06 | no | low latency, no reasoning step [S16] |
| gpt-5.4-mini | 400k (272k in) / 128k | 2025-08 | none…xhigh | "strongest mini model yet"; beats gpt-5-mini on GPQA 88.0 vs 81.6 and τ²-bench 93.4 vs 74.1 (at xhigh vs high) [S10, S21] |
| gpt-5.4 | 1.05M / 128k | 2025-08 | none…xhigh | flagship of the 5.4 family [S9] |

OpenAI publishes no structured-extraction benchmark for these models.

**Recommendation (pending our benchmark).**
- **Extraction:** `gpt-5.4-mini`, effort `none` (or `low` if dates and deadlines suffer). It is in
  the 2.5M pool (~200 pages/day), has a fresh cutoff, and no shutdown is announced. Run the
  benchmark first against `gpt-4.1-mini`, and against `gpt-4o`/`gpt-5.4` as the quality ceiling.
- **gpt-4o** (the owner's suggestion): good structured-output support, but it uses the 250k pool
  (~20 pages/day), has the oldest cutoff (weak on "which year?"), and is 3× pricier per input
  token than 5.4-mini. Use it as a baseline, not as the default.
- **Relevance classification:** `gpt-5.4-mini` with effort `none`, an enum schema, and a ~1–2k
  token input (title + snippet).
- **Turkish summary:** `gpt-5.4-mini`. The large pool (`gpt-5.4`) is reserved for re-tries on
  low-confidence pages.
- **Discovery agent:** `gpt-5.4-mini` with `web_search` (paid, under a cap) or with our own search
  and the free pool.
- Make the model configurable per task: `OPENAI_MODEL_EXTRACT`, `_CLASSIFY` and `_SUMMARY`, each
  defaulting to `OPENAI_MODEL`.

## 5. Implementation sketch

**Finding:** the official SDK `openai` **3.x (3.0.0, 2026-08-12 → 3.29.0, 2026-10-11) depends on
`httpx2<3,>=2.12.0`, not `httpx`** (PyPI metadata). 2.x used `httpx`. So the SDK no longer
conflicts with D-20. It also adds `anyio`, `jiter`, `sniffio` and `typing-extensions`, and it
ships several releases a week.

**Recommendation: raw REST over httpx2 (`llm/openai.py`), no SDK.** Reasons:
- It matches `OllamaProvider`: the same transport, the same error mapping, the same
  `httpx2.MockTransport` tests.
- We need one endpoint, plus `GET /v1/models/{model}` for `health()`.
- D-10 favours minimal dependencies, and the SDK's release churn is an extra supply-chain
  surface.
- The SDK conveniences we would lose (retries, `output_text`) are about 40 lines.

Revisit if we need streaming or background mode.

```
POST https://api.openai.com/v1/responses
Authorization: Bearer $OPENAI_API_KEY   (optional: OpenAI-Project: $OPENAI_PROJECT_ID)
{ "model": "gpt-5.4-mini", "store": false,
  "instructions": "<system prompt>",                    // our SYSTEM_PROMPT
  "input": [{"role": "user", "content": "<user msg>"}], // untrusted envelope here only
  "reasoning": {"effort": "none"},                      // gpt-5.x only; temperature 0 ok at none
  "max_output_tokens": 4000,
  "text": {"format": {"type": "json_schema", "name": "ExtractionOutput",
                      "strict": true, "schema": { ...to_strict_schema(...) }}} }
```

Response handling:
- `status` "completed", "incomplete" or "failed". `incomplete_details.reason`. `error`.
- `output[]` → the item with `type: "message"` → `content[]`. The text is in `{type:
  "output_text", text}`; a refusal is `{type: "refusal", refusal}` → `LLMOutputError`.
- `usage.input_tokens`, `usage.input_tokens_details.cached_tokens` and `usage.output_tokens`
  (all three verified live 2026-10-13),
  `usage.output_tokens_details.reasoning_tokens`, `usage.total_tokens`.
- Log the `billing` field when present (community report, **[UNVERIFIED]**).

Error mapping:
- timeout → `LLMTimeoutError`
- connect error → `LLMUnavailableError`
- 401/403 → `LLMConfigError`-like `LLMError` (the message never contains the key)
- 404 model → `LLMModelMissingError`
- 429 quota or spend → `LLMError("quota")`, no retry
- 429 rate, 500, 503 → up to 2 retries with backoff
- `health()` → `GET /v1/models/{model}`

Guards:
- `PIIGuard` (§1) runs before every send.
- A daily token counter (persisted) refuses calls above the configured pool budget.
- `trust_env=False`, `follow_redirects=False`, the key held only in memory, `__repr__` without
  the key.

**Config keys (proposed):**
- `LLM_PROVIDER=openai|ollama`
- `OPENAI_API_KEY` (secret, `.env` only)
- `OPENAI_MODEL=gpt-5.4-mini`
- `OPENAI_PROJECT_ID` (optional)
- `OPENAI_BASE_URL=https://api.openai.com/v1`. The EU residency endpoint `eu.api.openai.com`
  needs prior approval [S1].
- `OPENAI_TIMEOUT_S=90`
- `OPENAI_MAX_RETRIES=2`
- `OPENAI_REASONING_EFFORT=none`
- `OPENAI_MAX_OUTPUT_TOKENS=4000`
- `OPENAI_DAILY_TOKEN_BUDGET=2000000`, kept below the 2.5M pool

**First tests (before any code is relied on):**
1. Strict mode with and without `maxLength`. **Verified live 2026-10-13:** accepted.
2. Does a Responses call show zero cost in Usage vs Costs? Open.
3. Does gpt-5.4-mini accept `temperature` at effort `none`? **Verified live 2026-10-13:** yes.
4. Does the cached-input share count against the pool? Open.

**Verified live 2026-10-13** (owner's key, `POST /v1/responses`, `store: false`):
- gpt-5.4-mini, effort `none`, strict `json_schema` with `maxLength` and `minimum`: completed,
  correct output. Same call with `temperature: 0`: accepted.
- gpt-4o, `temperature: 0`, strict + `maxLength`: accepted. No `reasoning` param is sent to
  gpt-4o or gpt-4.1-*.
- `usage.input_tokens`, `usage.input_tokens_details.cached_tokens`, `usage.output_tokens`
  present. Header `x-ratelimit-remaining-tokens` was 2000000 for gpt-5.4-mini and 449912 for
  gpt-4o (the provider logs it at debug level, never with the key).

**Implemented (2026-10-13):** `services/api/src/fhc_api/llm/openai.py` (+ `pii.py`). The daily
token counter is in-process (per UTC day, lost on restart). **Follow-up:** a DB-backed counter
that survives restarts and is shared by every process.

## 6. Prompt injection with untrusted web content

OpenAI guidance [S12, S22], mapped to what we already do (`llm/untrusted.py`):
- **Untrusted input goes in user messages, never developer/system messages.** "Injecting untrusted
  input directly into developer messages gives attackers the highest degree of control." Already
  our rule: page text goes only in the user message inside the random-boundary envelope. In
  Responses, `instructions` holds only our own text.
- **Structured outputs remove freeform channels.** Enums and fixed schemas "eliminate freeform
  channels that attackers can exploit to smuggle instructions or data". Our strict schema plus
  per-field validation plus the snippet-evidence check already apply this.
- **Untrusted data must never directly drive agent behaviour.** Code chooses the next step. For
  discovery: no tools other than `web_search`, no function tools that write, and every URL the
  model returns is re-fetched and re-validated by our pipeline. Never follow model-chosen URLs
  with credentials.
- Limit input and output length (we cap at 24k chars and set `max_output_tokens`). Keep a human
  in the loop: imports stay drafts until an admin approves them. Red-team: add injection fixtures
  to the benchmark. Use guardrails such as PII redaction as a first line only [S12, S22].
- OpenAI states these measures reduce the risk but "don't fully remove" it [S22].

## Sources (accessed 2026-10-13)

- S1 Your data — https://developers.openai.com/api/docs/guides/your-data
- S2 Help: Sharing … API inputs and outputs with OpenAI (403; via search snippets) —
  https://help.openai.com/en/articles/10306912-sharing-feedback-evaluation-and-fine-tuning-data-and-api-inputs-and-outputs-with-openai
- S3 Community: extended free tokens — https://community.openai.com/t/good-news-extended-free-tokens-on-traffic-shared-with-openai/1241322
- S4 Community billing reports — https://community.openai.com/t/im-being-charged-for-free-tokens/1367889 ,
  https://community.openai.com/t/complimentary-tokens-gpt-5-4-mini-is-charged-for-1m-token-group-rather-than-10m-token-group/1377453
- S5 Spend limits — https://developers.openai.com/api/docs/guides/spend-limits
- S6 Migrate to Responses — https://developers.openai.com/api/docs/guides/migrate-to-responses
- S7 Web search tool — https://developers.openai.com/api/docs/guides/tools-web-search
- S8 Structured Outputs — https://developers.openai.com/api/docs/guides/structured-outputs
- S9 gpt-5.4 — https://developers.openai.com/api/docs/models/gpt-5.4
- S10 gpt-5.4-mini — https://developers.openai.com/api/docs/models/gpt-5.4-mini
- S11 Rate limits — https://developers.openai.com/api/docs/guides/rate-limits
- S12 Safety best practices — https://developers.openai.com/api/docs/guides/safety-best-practices
- S13 Reasoning — https://developers.openai.com/api/docs/guides/reasoning
- S14 Latest model guide — https://developers.openai.com/api/docs/guides/latest-model
- S15 gpt-4o — https://developers.openai.com/api/docs/models/gpt-4o
- S16 gpt-4.1-mini — https://developers.openai.com/api/docs/models/gpt-4.1-mini
- S17 Error codes — https://developers.openai.com/api/docs/guides/error-codes
- S18 openai-python README — https://github.com/openai/openai-python/blob/main/README.md ; PyPI metadata https://pypi.org/pypi/openai/json
- S19 Pricing — https://developers.openai.com/api/docs/pricing
- S20 Deprecations — https://developers.openai.com/api/docs/deprecations
- S21 Introducing GPT-5.4 mini and nano — https://openai.com/index/introducing-gpt-5-4-mini-and-nano/
- S22 Safety in building agents — https://developers.openai.com/api/docs/guides/agent-builder-safety
