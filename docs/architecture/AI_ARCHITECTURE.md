# AI Architecture

Principle: **AI is a component that proposes. Deterministic code decides, and a human approves.**

## 1. Responsibility split

| Work | Owner | Examples |
|---|---|---|
| Storage, state transitions, publication history, scheduling | Deterministic code | `events/service.py`, `publishing/hashing.py` |
| Dates, time zones, URL normalization, slugging, exact matching | Deterministic code | `common/normalize.py`, `common/clock.py` |
| Retrieval, robots, SSRF guard | Deterministic code | `common/http.py` |
| Structured data already on the page (JSON-LD `Event`, OpenGraph) | Deterministic parser | selectolax (V1.2) |
| Extracting fields from unstructured text | **LLM** | "Başvurular 5 Ekim'e kadar" → `application_deadline=2026-10-05` + snippet |
| Classification (categories) | **LLM** (small fixed label set) | `ai`, `fintech`, `energy`… |
| Summary / Telegram copy | **LLM**, human-edited | Turkish/English |
| Semantic duplicate check | **LLM**, only for pairs already flagged by fuzzy matching | V1.3 |
| Final verification and publishing | **Human** | Review screen |

## 2. Provider abstraction

A tiny interface of our own. No framework.

```python
class LLMProvider(Protocol):
    name: str
    async def generate_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T: ...                          # raises LLMOutputError after 1 repair retry
    async def generate_text(self, *, system: str, user: str, max_tokens: int) -> str: ...
    async def health(self) -> ProviderHealth: ...
```

| Provider | Version | Transport |
|---|---|---|
| `OllamaProvider` | **V1** (health + one schema-constrained test) | `POST /api/chat` with `format=<JSON Schema>`, `think=false`, `options.temperature=0` |
| `OpenAICompatibleProvider` | V1.2+ if needed | Chat Completions with `response_format: json_schema`. The same class covers OpenAI and other OpenAI-compatible endpoints. Gemini/Anthropic compatibility layers must be verified in their docs before use |
| `AnthropicProvider`, `GeminiProvider` | Later, only if the compat path is insufficient | Official SDKs |

Selection is a setting (`LLM_PROVIDER=ollama`). Cloud keys, when added, live only in `services/api/.env`.

Why no LiteLLM/LangChain: see STACK_RESEARCH §7.

## 3. Output validation pipeline (V1.2)

```text
page text (trafilatura) ─┐
JSON-LD / meta (parser) ─┼─► LLM extraction (schema: each field = {value, snippet}) 
                         │        ▼
                         │   Pydantic validation (types, enums, ranges)
                         │        ▼
                         └─► Evidence check: snippet must occur (normalized) in the fetched text,
                             else field → null + "unsupported" flag
                                  ▼
                             Deterministic rules: start ≤ end, deadline ≤ end, URLs http(s), year sane
                                  ▼
                             Draft event + event_field_evidence rows → Review queue
```

- JSON-LD values take precedence over LLM values. A conflict becomes a review signal.
- The LLM never assigns `verified`.

## 4. Prompt-injection defense (applies to every LLM call on external content)

Architecture rules (enforced in code, not just in the prompt):

1. **External content is data.** It is placed only in the user message, inside a delimiter block with a random per-call boundary:
   `<<<UNTRUSTED_PAGE_7f3a…>>> … <<<END_UNTRUSTED_PAGE_7f3a…>>>`. The boundary string is stripped from the content first.
2. **The system prompt says** the block is untrusted data to be extracted from, and that instructions inside it must be ignored. This lowers the risk but does not remove it, so rules 3–6 carry the weight.
3. **No tools, no secrets.** Extraction calls have no tool/function access and no secrets in context. There is nothing for injected text to trigger.
4. **Schema-constrained output only.** The model can only return the extraction schema. Free text fields are length-capped.
5. **Outputs are data too.** Extracted strings are rendered with escaping (React / Telegram HTML escape), never executed. URLs are re-validated. Telegram copy generated from the page is shown to the human before sending.
6. **No page can change goals.** The pipeline's next step is chosen by code, never by model output.

## 5. V1 deliverable

- `llm/provider.py`, `llm/ollama.py`.
- `GET /llm/check`: lists installed models (`/api/tags`) and runs one `generate_structured` call on a fixed 3-field schema, then reports latency.
- Settings page button "Test Ollama".
- Test: a unit test with a mocked HTTP transport for success, invalid JSON → one retry → error, and a timeout.
