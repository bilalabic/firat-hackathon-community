"""OpenAI provider over the Responses REST API (docs/research/OPENAI_API_RESEARCH.md §2, §5).

- `POST {base}/v1/responses` with `store: false`. `instructions` holds only our own system
  prompt; the user message (the only place for the untrusted envelope) goes in `input`.
  Structured output uses `text.format` = `json_schema` with `strict: true` and the schema from
  `to_strict_schema`. The reply is validated with Pydantic, with one repair retry.
- `GET {base}/v1/models/{model}` for `health()`.

Guards (D-23):
- Every outbound system/user string passes through `mask_pii` (KVKK) before the HTTP call.
- An in-process, per-UTC-day token counter refuses calls once the configured budget is used
  (follow-up: a DB-backed counter that survives restarts). The real limit is the project's
  hard spend limit on the OpenAI side.
- The API key lives only in this object; error messages carry the HTTP status and OpenAI's
  error code/type, never the key, the request body or OpenAI's free-text message (a 401
  message echoes part of the key).

Verified live 2026-10-13 (research §2): gpt-5.4-mini at effort `none` accepts `temperature: 0`
and a strict schema with `maxLength`/`minimum`; gpt-4o accepts `temperature: 0` and strict +
`maxLength`. Still configurable, because model families differ: which models take
`reasoning.effort` (`reasoning`), whether `temperature` is sent (`send_temperature`) and the
429 codes that mean quota or spend exhaustion (`quota_error_codes`).

Retries: connection errors and HTTP 408/429 (rate limit)/500/502/503/504, up to `max_retries`
times, with exponential backoff and jitter, honouring `Retry-After`/`retry-after-ms`. A read
timeout is not retried: OpenAI may still be generating (and billing) the first request.
Configuration is injected through the constructor; this module reads no environment variables.
"""

import ipaddress
import logging
import random
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote, urlsplit

import httpx2
from pydantic import ValidationError

from fhc_api.llm.ollama import REPAIR_INSTRUCTION, _format_validation_errors
from fhc_api.llm.pii import mask_pii
from fhc_api.llm.provider import (
    HealthStatus,
    LLMConfigError,
    LLMError,
    LLMModelMissingError,
    LLMOutputError,
    LLMTimeoutError,
    LLMUnavailableError,
    ProviderHealth,
    T,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com"
DEFAULT_MAX_OUTPUT_TOKENS = 4000
DEFAULT_MAX_RETRIES = 2

REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})
# Models that take `reasoning.effort`. They accept `temperature` only at effort `none`
# (verified for gpt-5.4-mini); non-reasoning models (gpt-4o, gpt-4.1-*) get no `reasoning`.
REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")

RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
# 429 codes that mean "no money/quota left": never retried.
QUOTA_ERROR_CODES = frozenset(
    {
        "insufficient_quota",
        "billing_hard_limit_reached",
        "project_spend_limit_exceeded",
        "spend_limit_exceeded",
        "credit_balance_exhausted",
    }
)
BACKOFF_BASE_S = 0.5
MAX_RETRY_DELAY_S = 30.0

_MAX_ECHOED_OUTPUT = 2000
_API_KEY_RE = re.compile(r"[\x21-\x7e]{20,512}")
_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]{0,99}")
_CODE_RE = re.compile(r"[a-z0-9_.\-]{1,64}")
_SCHEMA_NAME_RE = re.compile(r"[^A-Za-z0-9_\-]")

# -- strict schema -----------------------------------------------------------------------------

# Keywords strict mode rejects or that only add noise. Length caps and numeric ranges are kept
# (`maxLength`/`minimum` verified live 2026-10-13); Pydantic re-checks everything afterwards.
_DROPPED_KEYWORDS = frozenset(
    {
        "title",
        "default",
        "examples",
        "not",
        "if",
        "then",
        "else",
        "dependentRequired",
        "dependentSchemas",
        "discriminator",
        "readOnly",
        "writeOnly",
        "deprecated",
        "uniqueItems",
        "$schema",
        "$id",
    }
)
_STRICT_FORMATS = frozenset(
    {"date-time", "time", "date", "duration", "email", "hostname", "ipv4", "ipv6", "uuid"}
)
_NAMED_SUBSCHEMAS = frozenset({"properties", "$defs", "definitions"})


def to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a Pydantic JSON schema into one that Structured Outputs accepts with strict=true.

    Every object gets `additionalProperties: false` and lists all its properties in `required`
    (optional values stay expressible as `anyOf [..., {"type": "null"}]`). Unsupported keywords
    and formats are dropped; a single-element `allOf` is inlined. Free-form maps and multi-part
    `allOf` cannot be expressed and raise LLMConfigError. The input is not modified.
    """
    strict = _strict_node(schema)
    if not isinstance(strict, dict) or strict.get("type") != "object":
        raise LLMConfigError("Strict structured output needs an object at the schema root.")
    return strict


def _strict_node(node: Any) -> Any:
    if isinstance(node, list):
        return [_strict_node(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROPPED_KEYWORDS:
            continue
        if key == "format" and value not in _STRICT_FORMATS:
            continue
        if key in _NAMED_SUBSCHEMAS and isinstance(value, dict):
            # Keys here are names (a property may be called "title"), not keywords.
            out[key] = {name: _strict_node(sub) for name, sub in value.items()}
        else:
            out[key] = _strict_node(value)
    if "allOf" in out:
        parts = out.pop("allOf")
        if not (isinstance(parts, list) and len(parts) == 1 and isinstance(parts[0], dict)):
            raise LLMConfigError("Strict structured output does not support allOf.")
        for key, value in parts[0].items():
            out.setdefault(key, value)
    if out.get("type") == "object" or "properties" in out:
        extra = node.get("additionalProperties")
        if extra is True or isinstance(extra, dict):
            raise LLMConfigError("Strict structured output does not support free-form maps.")
        properties = out.setdefault("properties", {})
        out["required"] = list(properties)
        out["additionalProperties"] = False
    return out


# -- helpers -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cached_input_tokens + other.cached_input_tokens,
            self.reasoning_tokens + other.reasoning_tokens,
            self.total_tokens + other.total_tokens,
        )


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _parse_usage(payload: dict[str, Any]) -> TokenUsage:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return TokenUsage()
    input_details = usage.get("input_tokens_details")
    output_details = usage.get("output_tokens_details")
    input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=_int(
            input_details.get("cached_tokens") if isinstance(input_details, dict) else None
        ),
        reasoning_tokens=_int(
            output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None
        ),
        total_tokens=_int(usage.get("total_tokens")) or input_tokens + output_tokens,
    )


def _safe_code(value: Any) -> str | None:
    """An OpenAI identifier (`insufficient_quota`, `completed`, …) or None. Anything else,
    including anything key-shaped, is never echoed."""
    if not isinstance(value, str) or not _CODE_RE.fullmatch(value) or value.startswith("sk-"):
        return None
    return value


def _error_code(response: httpx2.Response) -> str | None:
    """OpenAI's `error.code` (or `error.type`), only if it looks like an identifier."""
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None
    return _safe_code(error.get("code")) or _safe_code(error.get("type"))


def _retry_after_s(response: httpx2.Response) -> float | None:
    for header, scale in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        raw = response.headers.get(header)
        if raw is None:
            continue
        try:
            seconds = float(raw) / scale
        except ValueError:
            continue  # an HTTP date: fall back to our own backoff
        if seconds >= 0:
            return min(seconds, MAX_RETRY_DELAY_S)
    return None


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validated_base_url(base_url: str) -> str:
    parts = urlsplit(base_url.strip())
    if not parts.hostname or parts.scheme not in ("http", "https"):
        raise LLMConfigError("OpenAI base URL must be an absolute https URL.")
    if parts.scheme == "http" and not _is_loopback(parts.hostname):
        raise LLMConfigError("OpenAI base URL must use https (http only for localhost).")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise LLMConfigError("OpenAI base URL must not contain credentials, query or fragment.")
    path = parts.path.rstrip("/")
    path = path.removesuffix("/v1")  # accept both https://api.openai.com and …/v1
    return f"{parts.scheme}://{parts.netloc}{path}"


def _model_prefixed(model: str, prefixes: tuple[str, ...]) -> bool:
    return model.lower().startswith(prefixes)


@dataclass
class _Reply:
    text: str
    incomplete_reason: str | None


@dataclass
class _DailyCounter:
    budget: int
    day: date
    used: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


# -- provider ----------------------------------------------------------------------------------


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float,
        client: httpx2.Client | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        reasoning_effort: str | None = "none",
        reasoning: bool | None = None,
        send_temperature: bool | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        daily_token_budget: int = 2_000_000,
        quota_error_codes: frozenset[str] = QUOTA_ERROR_CODES,
        sleep: Callable[[float], None] = time.sleep,
        utc_now: Callable[[], datetime] = lambda: datetime.now(UTC),
        jitter: Callable[[], float] = random.random,
    ) -> None:
        """`reasoning`: None picks from the model name (REASONING_MODEL_PREFIXES); True/False
        forces it. `reasoning_effort` None omits `reasoning` even for reasoning models.
        `send_temperature`: None sends it to non-reasoning models and to reasoning models at
        effort `none` only; True/False forces it."""
        if not _API_KEY_RE.fullmatch(api_key or ""):
            # Never echo the value: a mistyped key is still a secret.
            raise LLMConfigError("OpenAI API key is missing or has an invalid format.")
        model = model.strip()
        if not _MODEL_RE.fullmatch(model):
            raise LLMConfigError("OpenAI model name is empty or has invalid characters.")
        if timeout_s <= 0:
            raise LLMConfigError("OpenAI timeout must be positive.")
        if reasoning_effort is not None and reasoning_effort not in REASONING_EFFORTS:
            raise LLMConfigError(
                f"OpenAI reasoning effort must be one of {', '.join(sorted(REASONING_EFFORTS))}."
            )
        if max_output_tokens <= 0:
            raise LLMConfigError("OpenAI max_output_tokens must be positive.")
        if max_retries < 0:
            raise LLMConfigError("OpenAI max_retries must not be negative.")
        if daily_token_budget <= 0:
            raise LLMConfigError("OpenAI daily token budget must be positive.")
        self._base_url = _validated_base_url(base_url)
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        is_reasoning = (
            _model_prefixed(model, REASONING_MODEL_PREFIXES) if reasoning is None else reasoning
        )
        self._reasoning_effort = reasoning_effort if is_reasoning else None
        if send_temperature is None:
            send_temperature = not is_reasoning or self._reasoning_effort == "none"
        self._send_temperature = send_temperature
        self._max_output_tokens = max_output_tokens
        self._max_retries = max_retries
        self._quota_codes = quota_error_codes
        self._sleep = sleep
        self._utc_now = utc_now
        self._jitter = jitter
        self._counter = _DailyCounter(daily_token_budget, utc_now().date())
        self._total_usage = TokenUsage()
        # Usage of the latest generate_* call (including its repair retry). With concurrent
        # callers this is "some recent call"; use total_usage deltas for exact accounting.
        self.last_usage: TokenUsage | None = None
        self._owns_client = client is None
        # trust_env=False: no environment proxy sees the key; no redirects with the header.
        self._client = client or httpx2.Client(trust_env=False, follow_redirects=False)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def total_usage(self) -> TokenUsage:
        return self._total_usage

    @property
    def tokens_used_today(self) -> int:
        with self._counter.lock:
            self._roll_day()
            return self._counter.used

    @property
    def daily_token_budget(self) -> int:
        return self._counter.budget

    def __repr__(self) -> str:
        return f"OpenAIProvider(base_url={self._base_url!r}, model={self._model!r})"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- budget ------------------------------------------------------------------------------

    def _roll_day(self) -> None:
        # Caller holds the lock.
        today = self._utc_now().date()
        if today != self._counter.day:
            self._counter.day = today
            self._counter.used = 0

    def _check_budget(self) -> None:
        with self._counter.lock:
            self._roll_day()
            used, budget = self._counter.used, self._counter.budget
        if used >= budget:
            raise LLMError(
                f"OpenAI daily token budget reached ({used} of {budget} tokens used today; "
                "resets at 00:00 UTC)."
            )

    def _record(self, usage: TokenUsage) -> None:
        with self._counter.lock:
            self._roll_day()
            self._counter.used += usage.total_tokens
            self._total_usage += usage

    # -- transport ---------------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _status_error(self, response: httpx2.Response, code: str | None) -> LLMError:
        status = response.status_code
        suffix = f", {code}" if code else ""
        if status == 401:
            return LLMConfigError(
                f"OpenAI rejected the API key (HTTP 401{suffix}). Check OPENAI_API_KEY."
            )
        if status == 403:
            return LLMConfigError(
                f"OpenAI refused access (HTTP 403{suffix}): project, model or region."
            )
        if status == 404:
            return LLMModelMissingError(
                f"Model {self._model!r} is not available to this OpenAI project, or the base "
                f"URL is wrong (HTTP 404{suffix})."
            )
        if status == 429 and code in self._quota_codes:
            return LLMError(f"OpenAI quota or spend limit reached (HTTP 429{suffix}).")
        if status == 429:
            return LLMError(f"OpenAI rate limit still hit after retries (HTTP 429{suffix}).")
        if status >= 500:
            return LLMUnavailableError(f"OpenAI is unavailable (HTTP {status}{suffix}).")
        return LLMError(f"OpenAI rejected the request (HTTP {status}{suffix}).")

    def _backoff_s(self, attempt: int, response: httpx2.Response | None) -> float:
        if response is not None and (after := _retry_after_s(response)) is not None:
            return after
        delay = BACKOFF_BASE_S * (2.0**attempt) * (1 + 0.25 * self._jitter())
        return min(delay, MAX_RETRY_DELAY_S)

    def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        """Send one request (with retries) and return the decoded JSON body.

        httpx2 exceptions are converted outside the `except` block so that no request object
        (which carries the Authorization header) is chained onto the error we raise.
        """
        url = f"{self._base_url}{path}"
        attempt = 0
        while True:
            error: LLMError | None = None
            retryable = False
            response: httpx2.Response | None = None
            try:
                response = self._client.request(
                    method, url, json=json, headers=self._headers(), timeout=self._timeout_s
                )
            except httpx2.TimeoutException:
                error = LLMTimeoutError(f"OpenAI did not answer within {self._timeout_s:g} s.")
            except httpx2.ConnectError:
                error = LLMUnavailableError("Cannot connect to the OpenAI API.")
                retryable = True
            except httpx2.HTTPError as exc:
                error = LLMError(f"OpenAI request failed ({type(exc).__name__}).")

            if response is not None:
                remaining = response.headers.get("x-ratelimit-remaining-tokens")
                if remaining is not None and remaining.isdigit():
                    logger.debug("OpenAI x-ratelimit-remaining-tokens=%s", remaining)
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError:
                        error = LLMError("OpenAI returned a response that is not JSON.")
                else:
                    code = _error_code(response)
                    error = self._status_error(response, code)
                    retryable = response.status_code in RETRY_STATUSES and not (
                        response.status_code == 429 and code in self._quota_codes
                    )

            assert error is not None  # noqa: S101 - every branch above sets it
            if not retryable or attempt >= self._max_retries:
                raise error
            delay = self._backoff_s(attempt, response)
            logger.info(
                "OpenAI %s %s failed (%s); retry %d/%d in %.1f s",
                method,
                path,
                type(error).__name__,
                attempt + 1,
                self._max_retries,
                delay,
            )
            self._sleep(delay)
            attempt += 1

    def _respond(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_output_tokens: int,
        text_format: dict[str, Any] | None,
        usage_sink: list[TokenUsage],
    ) -> _Reply:
        self._check_budget()
        body: dict[str, Any] = {
            "model": self._model,
            "store": False,
            # KVKK guard: nothing leaves without masking (instructions and every message).
            "instructions": mask_pii(system),
            "input": [{"role": m["role"], "content": mask_pii(m["content"])} for m in messages],
            "max_output_tokens": max_output_tokens,
        }
        if self._reasoning_effort is not None:
            body["reasoning"] = {"effort": self._reasoning_effort}
        if self._send_temperature:
            body["temperature"] = temperature
        if text_format is not None:
            body["text"] = {"format": text_format}

        payload = self._request("POST", "/v1/responses", json=body)
        if not isinstance(payload, dict):
            raise LLMError("OpenAI response is not a JSON object.")
        usage = _parse_usage(payload)
        self._record(usage)
        usage_sink.append(usage)
        billing = payload.get("billing")
        logger.info(
            "OpenAI response model=%s status=%s input=%d output=%d reasoning=%d payer=%s",
            self._model,
            _safe_code(payload.get("status")),
            usage.input_tokens,
            usage.output_tokens,
            usage.reasoning_tokens,
            _safe_code(billing.get("payer")) if isinstance(billing, dict) else None,
        )
        return self._parse_reply(payload)

    @staticmethod
    def _parse_reply(payload: dict[str, Any]) -> _Reply:
        status = payload.get("status")
        if status == "failed":
            error = payload.get("error")
            code = _safe_code(error.get("code")) if isinstance(error, dict) else None
            raise LLMError(f"OpenAI response failed{f' ({code})' if code else ''}.")
        incomplete_reason: str | None = None
        if status == "incomplete":
            details = payload.get("incomplete_details")
            incomplete_reason = (
                _safe_code(details.get("reason")) if isinstance(details, dict) else None
            ) or "unknown"
        texts: list[str] = []
        output = payload.get("output")
        for item in output if isinstance(output, list) else []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            for part in content if isinstance(content, list) else []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "refusal":
                    raise LLMOutputError("The model refused to answer.")
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        if not texts and incomplete_reason is None:
            raise LLMError("OpenAI response has no output text.")
        return _Reply("".join(texts), incomplete_reason)

    # -- LLMProvider -------------------------------------------------------------------------

    def generate_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T:
        text_format = {
            "type": "json_schema",
            "name": _SCHEMA_NAME_RE.sub("_", schema.__name__)[:64] or "output",
            "strict": True,
            "schema": to_strict_schema(schema.model_json_schema()),
        }
        messages = [{"role": "user", "content": user}]
        usage: list[TokenUsage] = []
        try:
            content = self._structured_text(system, messages, temperature, text_format, usage)
            try:
                return schema.model_validate_json(content)
            except ValidationError as exc:
                first_error = exc

            # Exactly one repair retry, as in OllamaProvider: only the model's own output and
            # the validation messages (no input values) are added.
            messages += [
                {"role": "assistant", "content": content[:_MAX_ECHOED_OUTPUT]},
                {
                    "role": "user",
                    "content": REPAIR_INSTRUCTION.format(
                        errors=_format_validation_errors(first_error)
                    ),
                },
            ]
            content = self._structured_text(system, messages, temperature, text_format, usage)
            try:
                return schema.model_validate_json(content)
            except ValidationError as exc:
                count = exc.error_count()
            raise LLMOutputError(
                f"Model output did not match schema {schema.__name__} after one repair retry "
                f"({count} validation error(s))."
            )
        finally:
            self.last_usage = sum(usage, TokenUsage())

    def _structured_text(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float,
        text_format: dict[str, Any],
        usage: list[TokenUsage],
    ) -> str:
        reply = self._respond(
            system=system,
            messages=messages,
            temperature=temperature,
            max_output_tokens=self._max_output_tokens,
            text_format=text_format,
            usage_sink=usage,
        )
        if reply.incomplete_reason is not None:
            # A cut-off JSON object cannot be repaired by asking again with the same limit.
            raise LLMOutputError(
                f"OpenAI output was incomplete ({reply.incomplete_reason}); "
                "raise OPENAI_MAX_OUTPUT_TOKENS or shorten the input."
            )
        return reply.text

    def generate_text(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive.")
        usage: list[TokenUsage] = []
        try:
            reply = self._respond(
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=temperature,
                max_output_tokens=max_tokens,
                text_format=None,
                usage_sink=usage,
            )
        finally:
            self.last_usage = sum(usage, TokenUsage())
        # A text cut at max_tokens is what the caller asked for.
        return reply.text

    def health(self) -> ProviderHealth:
        def result(status: HealthStatus, message: str) -> ProviderHealth:
            return ProviderHealth(
                provider=self.name,
                status=status,
                configured_model=self._model,
                installed_models=[self._model] if status == "ok" else [],
                message=message,
            )

        url = f"{self._base_url}/v1/models/{quote(self._model, safe='')}"
        error: str | None = None
        status: HealthStatus = "error"
        try:
            response = self._client.get(url, headers=self._headers(), timeout=self._timeout_s)
        except httpx2.TimeoutException:
            error, status = f"OpenAI did not answer within {self._timeout_s:g} s.", "not_running"
        except httpx2.ConnectError:
            error, status = "Cannot connect to the OpenAI API.", "not_running"
        except httpx2.HTTPError as exc:
            error = f"OpenAI request failed ({type(exc).__name__})."
        if error is not None:
            return result(status, error)

        if response.status_code == 200:
            budget = self._counter.budget
            return result(
                "ok",
                f"OpenAI API reachable and {self._model!r} is available "
                f"({self.tokens_used_today} of {budget} daily tokens used).",
            )
        problem = self._status_error(response, _error_code(response))
        if isinstance(problem, LLMModelMissingError):
            return result("model_missing", str(problem))
        if isinstance(problem, LLMUnavailableError):
            return result("not_running", str(problem))
        return result("error", str(problem))
