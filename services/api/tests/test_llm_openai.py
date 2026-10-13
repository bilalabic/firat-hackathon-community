"""OpenAIProvider over httpx2.MockTransport; no network calls."""

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel, Field

from fhc_api.importing.extraction import ExtractionOutput
from fhc_api.llm.openai import OpenAIProvider, TokenUsage, to_strict_schema
from fhc_api.llm.provider import (
    LLMConfigError,
    LLMError,
    LLMModelMissingError,
    LLMOutputError,
    LLMProvider,
    LLMTimeoutError,
    LLMUnavailableError,
)

BASE = "https://api.openai.com"
MODEL = "gpt-5.4-mini"
KEY = "sk-test-LEAKMARKER-0123456789abcdef"


class Sample(BaseModel):
    city: str
    year: int


class WithOptional(BaseModel):
    name: str | None = Field(default=None, max_length=10, title="Name")
    tags: list[str] = Field(default_factory=list)


Handler = Callable[[httpx2.Request], httpx2.Response]


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx2.Request] = []
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.content:
            self.bodies.append(json.loads(request.content))
        return self.handler(request)


def make_provider(
    handler: Handler, *, model: str = MODEL, **kwargs: Any
) -> tuple[OpenAIProvider, Recorder, list[float]]:
    recorder = Recorder(handler)
    sleeps: list[float] = []
    client = httpx2.Client(transport=httpx2.MockTransport(recorder))
    kwargs.setdefault("jitter", lambda: 0.0)
    kwargs.setdefault("sleep", sleeps.append)
    provider = OpenAIProvider(KEY, model, timeout_s=5, client=client, **kwargs)
    return provider, recorder, sleeps


def reply(
    text: str,
    *,
    status: str = "completed",
    input_tokens: int = 100,
    output_tokens: int = 20,
    extra: dict[str, Any] | None = None,
) -> httpx2.Response:
    body: dict[str, Any] = {
        "id": "resp_1",
        "object": "response",
        "status": status,
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            },
        ],
        "usage": {
            "input_tokens": input_tokens,
            "input_tokens_details": {"cached_tokens": 10},
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": input_tokens + output_tokens,
        },
        **(extra or {}),
    }
    return httpx2.Response(200, json=body)


def error(status: int, code: str | None, message: str = "x", **headers: str) -> httpx2.Response:
    return httpx2.Response(
        status,
        json={"error": {"message": message, "type": "error_type", "param": None, "code": code}},
        headers=headers,
    )


def sequence(*responses: httpx2.Response) -> Handler:
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return queue.pop(0)

    return handler


# -- success -----------------------------------------------------------------------------------


def test_satisfies_protocol_and_repr_hides_the_key() -> None:
    provider: LLMProvider = OpenAIProvider(KEY, MODEL, timeout_s=1)
    assert provider.name == "openai"
    assert KEY not in repr(provider)


def test_generate_structured_sends_documented_fields() -> None:
    provider, rec, _ = make_provider(sequence(reply('{"city": "Elazığ", "year": 2026}')))

    result = provider.generate_structured(system="sys", user="usr", schema=Sample)

    assert result == Sample(city="Elazığ", year=2026)
    (request,) = rec.requests
    assert request.method == "POST"
    assert str(request.url) == f"{BASE}/v1/responses"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    (body,) = rec.bodies
    assert body["model"] == MODEL
    assert body["store"] is False
    assert body["instructions"] == "sys"
    assert body["input"] == [{"role": "user", "content": "usr"}]
    assert body["reasoning"] == {"effort": "none"}
    assert body["temperature"] == 0.0  # accepted at effort none (verified live 2026-10-13)
    assert body["max_output_tokens"] == 4000
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "Sample",
        "strict": True,
        "schema": to_strict_schema(Sample.model_json_schema()),
    }
    assert provider.last_usage == TokenUsage(100, 20, 10, 0, 120)


def test_non_reasoning_model_gets_temperature_and_no_reasoning() -> None:
    provider, rec, _ = make_provider(
        sequence(reply('{"city": "x", "year": 1}')), model="gpt-4.1-mini"
    )

    provider.generate_structured(system="s", user="u", schema=Sample, temperature=0.3)

    assert rec.bodies[0]["temperature"] == 0.3
    assert "reasoning" not in rec.bodies[0]


def test_reasoning_model_above_effort_none_gets_no_temperature() -> None:
    provider, rec, _ = make_provider(sequence(reply("hi")), reasoning_effort="low")
    provider.generate_text(system="s", user="u", max_tokens=5)
    assert rec.bodies[0]["reasoning"] == {"effort": "low"}
    assert "temperature" not in rec.bodies[0]


def test_reasoning_and_temperature_can_be_forced() -> None:
    provider, rec, _ = make_provider(
        sequence(reply("hi")), reasoning_effort="low", send_temperature=True
    )

    provider.generate_text(system="s", user="u", max_tokens=50)

    assert rec.bodies[0]["reasoning"] == {"effort": "low"}
    assert rec.bodies[0]["temperature"] == 0.0
    assert rec.bodies[0]["max_output_tokens"] == 50
    assert "text" not in rec.bodies[0]


def test_reasoning_effort_none_omits_reasoning() -> None:
    provider, rec, _ = make_provider(sequence(reply("hi")), reasoning_effort=None)
    provider.generate_text(system="s", user="u", max_tokens=5)
    assert "reasoning" not in rec.bodies[0]


def test_base_url_with_v1_suffix_is_accepted() -> None:
    provider = OpenAIProvider(KEY, MODEL, timeout_s=1, base_url="https://api.openai.com/v1/")
    assert provider.base_url == BASE


# -- strict schema ------------------------------------------------------------------------------


def test_strict_schema_requires_every_property_and_forbids_extras() -> None:
    strict = to_strict_schema(WithOptional.model_json_schema())

    assert strict["required"] == ["name", "tags"]
    assert strict["additionalProperties"] is False
    assert "title" not in strict
    name = strict["properties"]["name"]
    # Nullable kept; maxLength kept (verified live 2026-10-13); title/default dropped.
    assert name == {"anyOf": [{"type": "string", "maxLength": 10}, {"type": "null"}]}
    assert "default" not in strict["properties"]["tags"]


def test_strict_schema_walks_defs_and_keeps_property_names() -> None:
    schema = ExtractionOutput.model_json_schema()
    strict = to_strict_schema(schema)

    assert set(strict["required"]) == set(schema["properties"])
    assert "title" in strict["properties"]  # a property called "title" is not dropped
    for definition in strict["$defs"].values():
        assert definition["additionalProperties"] is False
        assert definition["required"] == list(definition["properties"])
    dumped = json.dumps(strict)
    assert dumped.count("maxLength") == json.dumps(schema).count("maxLength")
    assert '"default"' not in dumped
    assert "additionalProperties" not in json.dumps(schema)  # input untouched


def test_strict_schema_keeps_numeric_ranges() -> None:
    class Ranged(BaseModel):
        year: int = Field(ge=2000, le=2100)

    strict = to_strict_schema(Ranged.model_json_schema())
    assert strict["properties"]["year"] == {"type": "integer", "minimum": 2000, "maximum": 2100}


def test_strict_schema_drops_unsupported_formats_and_keeps_supported() -> None:
    schema = {
        "type": "object",
        "properties": {
            "u": {"type": "string", "format": "uri"},
            "d": {"type": "string", "format": "date"},
        },
    }
    strict = to_strict_schema(schema)
    assert strict["properties"]["u"] == {"type": "string"}
    assert strict["properties"]["d"] == {"type": "string", "format": "date"}


def test_strict_schema_rejects_free_form_maps_and_non_object_root() -> None:
    class Mapping(BaseModel):
        values: dict[str, int]

    with pytest.raises(LLMConfigError, match="free-form"):
        to_strict_schema(Mapping.model_json_schema())
    with pytest.raises(LLMConfigError, match="root"):
        to_strict_schema({"anyOf": [{"type": "string"}, {"type": "null"}]})


_NOT_STRICT = {"title", "default", "allOf", "oneOf", "not", "prefixItems", "patternProperties"}


def assert_strict(node: object, defs: dict[str, object], path: str = "#") -> None:
    """Walk a schema and check the Structured Outputs strict rules (research §2)."""
    if isinstance(node, list):
        for i, item in enumerate(node):
            assert_strict(item, defs, f"{path}/{i}")
        return
    if not isinstance(node, dict):
        return
    assert not _NOT_STRICT & node.keys(), f"{path}: {sorted(_NOT_STRICT & node.keys())}"
    if "$ref" in node:
        assert node["$ref"].removeprefix("#/$defs/") in defs, path
    if node.get("type") == "object":
        assert node["additionalProperties"] is False, path
        assert node["required"] == list(node["properties"]), path
    for key, value in node.items():
        if key in {"properties", "$defs"}:
            for name, sub in value.items():
                assert_strict(sub, defs, f"{path}/{key}/{name}")
        elif key not in {"enum", "required", "const"}:
            assert_strict(value, defs, f"{path}/{key}")


def test_extraction_output_schema_converts_to_a_valid_strict_schema() -> None:
    strict = to_strict_schema(ExtractionOutput.model_json_schema())

    assert strict["type"] == "object"
    assert_strict(strict, strict["$defs"])
    # Nullable values, length caps and the format enum survive.
    text160 = strict["$defs"]["_Text160"]["properties"]["value"]
    assert text160 == {"anyOf": [{"type": "string", "maxLength": 160}, {"type": "null"}]}
    assert strict["$defs"]["_Date"]["properties"]["value"]["description"] == "YYYY-MM-DD"
    assert "enum" in json.dumps(strict)
    # A complete example still validates with the original model.
    example = {name: {"value": None, "snippet": None} for name in ExtractionOutput.model_fields}
    assert ExtractionOutput.model_validate(example)


@pytest.mark.parametrize(
    ("schema", "keyword"),
    [
        ({"type": "object", "properties": {"a": {"oneOf": [{"type": "string"}]}}}, "oneOf"),
        (
            {"type": "object", "properties": {"a": {"type": "array", "prefixItems": []}}},
            "prefixItems",
        ),
        (
            {"type": "object", "properties": {}, "patternProperties": {"^x": {}}},
            "patternProperties",
        ),
    ],
)
def test_strict_schema_rejects_keywords_it_cannot_express(
    schema: dict[str, Any], keyword: str
) -> None:
    with pytest.raises(LLMConfigError, match=keyword):
        to_strict_schema(schema)


def test_strict_schema_inlines_single_allof() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"allOf": [{"$ref": "#/$defs/X"}], "description": "d"}},
        "$defs": {"X": {"type": "object", "properties": {"b": {"type": "integer"}}}},
    }
    strict = to_strict_schema(schema)
    assert strict["properties"]["a"] == {"description": "d", "$ref": "#/$defs/X"}
    with pytest.raises(LLMConfigError, match="allOf"):
        to_strict_schema({"type": "object", "properties": {"a": {"allOf": [{}, {}]}}})


# -- repair, refusal, truncation ---------------------------------------------------------------


def test_invalid_output_is_repaired_once() -> None:
    class Capped(BaseModel):
        city: str = Field(max_length=3)

    provider, rec, _ = make_provider(
        sequence(reply('{"city": "Elazığ"}'), reply('{"city": "Elz"}', input_tokens=150))
    )

    result = provider.generate_structured(system="sys", user="usr", schema=Capped)

    assert result.city == "Elz"
    assert len(rec.bodies) == 2
    retry = rec.bodies[1]["input"]
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]
    assert retry[1]["content"] == '{"city": "Elazığ"}'
    assert "city:" in retry[2]["content"]
    assert rec.bodies[1]["text"] == rec.bodies[0]["text"]
    assert provider.last_usage is not None
    assert provider.last_usage.input_tokens == 250  # both calls of this generate_structured


def test_invalid_twice_raises_output_error() -> None:
    provider, rec, _ = make_provider(sequence(reply("not json"), reply("still not")))
    with pytest.raises(LLMOutputError, match="after one repair retry"):
        provider.generate_structured(system="s", user="u", schema=Sample)
    assert len(rec.bodies) == 2


def test_refusal_raises_output_error_without_retry() -> None:
    refusal = httpx2.Response(
        200,
        json={
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "refusal", "refusal": "no"}]},
            ],
            "usage": {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6},
        },
    )
    provider, rec, _ = make_provider(sequence(refusal))
    with pytest.raises(LLMOutputError, match="refused"):
        provider.generate_structured(system="s", user="u", schema=Sample)
    assert len(rec.bodies) == 1
    assert provider.tokens_used_today == 6


def test_incomplete_structured_output_is_not_repaired() -> None:
    truncated = reply(
        '{"city": "El',
        status="incomplete",
        extra={"incomplete_details": {"reason": "max_output_tokens"}},
    )
    provider, rec, _ = make_provider(sequence(truncated))
    with pytest.raises(LLMOutputError, match="max_output_tokens"):
        provider.generate_structured(system="s", user="u", schema=Sample)
    assert len(rec.bodies) == 1


def incomplete(text: str, reason: str) -> httpx2.Response:
    return reply(text, status="incomplete", extra={"incomplete_details": {"reason": reason}})


def test_text_cut_at_max_tokens_returns_what_arrived() -> None:
    provider, _, _ = make_provider(sequence(incomplete("Merh", "max_output_tokens")))
    assert provider.generate_text(system="s", user="u", max_tokens=2) == "Merh"


@pytest.mark.parametrize(
    ("response", "match"),
    [
        (incomplete("", "max_output_tokens"), "hit max_output_tokens"),
        (incomplete("Partial", "content_filter"), r"stopped the output \(content_filter\)"),
        (incomplete("Partial", "other_reason"), r"incomplete \(other_reason\)"),
    ],
)
def test_incomplete_text_without_usable_output_raises(
    response: httpx2.Response, match: str
) -> None:
    provider, _, _ = make_provider(sequence(response))
    with pytest.raises(LLMOutputError, match=match):
        provider.generate_text(system="s", user="u", max_tokens=5)


def test_structured_content_filter_is_worded_per_reason() -> None:
    provider, _, _ = make_provider(sequence(incomplete('{"city"', "content_filter")))
    with pytest.raises(LLMOutputError, match="content_filter") as info:
        provider.generate_structured(system="s", user="u", schema=Sample)
    assert "OPENAI_MAX_OUTPUT_TOKENS" not in str(info.value)


def test_multiple_message_and_reasoning_items_are_joined() -> None:
    body = {
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": '{"city": '}]},
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "ignored"}]},
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": '"x", '},
                    {"type": "output_text", "text": '"year": 1}'},
                ],
            },
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }
    provider, _, _ = make_provider(sequence(httpx2.Response(200, json=body)))
    assert provider.generate_structured(system="s", user="u", schema=Sample) == Sample(
        city="x", year=1
    )


def test_failed_response_raises() -> None:
    failed = httpx2.Response(
        200, json={"status": "failed", "error": {"code": "server_error", "message": "m"}}
    )
    provider, _, _ = make_provider(sequence(failed))
    with pytest.raises(LLMError, match="server_error"):
        provider.generate_text(system="s", user="u", max_tokens=5)


# -- error mapping and retries ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "expected", "match"),
    [
        (error(401, "invalid_api_key"), LLMConfigError, "HTTP 401"),
        (error(403, "unsupported_country_region_territory"), LLMConfigError, "HTTP 403"),
        (error(404, "model_not_found"), LLMModelMissingError, "not available"),
        (error(400, "invalid_json_schema"), LLMError, "HTTP 400, invalid_json_schema"),
        (error(429, "insufficient_quota"), LLMError, "quota or spend limit"),
        (error(429, "project_spend_limit_exceeded"), LLMError, "quota or spend limit"),
    ],
)
def test_errors_are_mapped_and_not_retried(
    response: httpx2.Response, expected: type[LLMError], match: str
) -> None:
    provider, rec, sleeps = make_provider(sequence(response))
    with pytest.raises(expected, match=match):
        provider.generate_structured(system="s", user="u", schema=Sample)
    assert len(rec.requests) == 1
    assert sleeps == []


def test_rate_limit_is_retried_honouring_retry_after() -> None:
    provider, rec, sleeps = make_provider(
        sequence(
            error(429, "rate_limit_exceeded", **{"retry-after": "3"}),
            error(503, "server_is_overloaded", **{"retry-after-ms": "250"}),
            reply('{"city": "x", "year": 1}'),
        )
    )
    assert provider.generate_structured(system="s", user="u", schema=Sample).year == 1
    assert len(rec.requests) == 3
    assert sleeps == [3.0, 0.25]


def test_server_errors_use_exponential_backoff_then_give_up() -> None:
    provider, rec, sleeps = make_provider(
        sequence(error(503, None), error(502, None), error(504, None))
    )
    with pytest.raises(LLMUnavailableError, match="HTTP 504"):
        provider.generate_text(system="s", user="u", max_tokens=5)
    assert len(rec.requests) == 3  # 1 + max_retries (2)
    assert sleeps == [0.5, 1.0]


def test_500_on_post_is_not_retried() -> None:
    # The work may have been done (and billed) before the 500.
    provider, rec, sleeps = make_provider(sequence(error(500, None), reply("ok")))
    with pytest.raises(LLMUnavailableError, match="HTTP 500"):
        provider.generate_text(system="s", user="u", max_tokens=5)
    assert len(rec.requests) == 1
    assert sleeps == []


def test_connect_timeout_is_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx2.ConnectTimeout("connect timed out", request=request)
        return reply("ok")

    provider, rec, sleeps = make_provider(handler)
    assert provider.generate_text(system="s", user="u", max_tokens=5) == "ok"
    assert len(rec.requests) == 2
    assert sleeps == [0.5]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_total_timeout_caps_retries_and_shrinks_the_attempt_timeout() -> None:
    clock = FakeClock()
    timeouts: list[float] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        timeouts.append(request.extensions["timeout"]["read"])
        clock.now += 4.0  # each attempt takes 4 s
        return error(503, None, **{"retry-after": "1"})

    provider, rec, _ = make_provider(
        handler, total_timeout_s=8, monotonic=clock, sleep=clock.sleep, max_retries=5
    )

    with pytest.raises(LLMUnavailableError, match="HTTP 503"):
        provider.generate_text(system="s", user="u", max_tokens=5)

    # t=0: attempt 1 (5 s timeout) -> t=4; sleep 1 -> t=5; attempt 2 gets the 3 s left -> t=9;
    # no time for a third attempt although max_retries allows it.
    assert timeouts == [5.0, 3.0]
    assert len(rec.requests) == 2
    assert clock.now == 9.0


def test_total_timeout_covers_the_repair_retry() -> None:
    clock = FakeClock()

    def handler(request: httpx2.Request) -> httpx2.Response:
        clock.now += 7.5
        return reply('{"city": "x"}')  # invalid: needs a repair

    provider, rec, _ = make_provider(handler, total_timeout_s=8, monotonic=clock, sleep=clock.sleep)
    with pytest.raises(LLMTimeoutError, match="total time budget"):
        provider.generate_structured(system="s", user="u", schema=Sample)
    assert len(rec.requests) == 1


def test_retry_after_is_capped() -> None:
    provider, _, sleeps = make_provider(
        sequence(error(429, None, **{"retry-after": "3600"}), reply("ok"))
    )
    provider.generate_text(system="s", user="u", max_tokens=5)
    assert sleeps == [30.0]


def test_connect_error_is_retried_and_timeout_is_not() -> None:
    calls: list[int] = []

    def flaky(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx2.ConnectError("refused", request=request)
        return reply("ok")

    provider, _, sleeps = make_provider(flaky)
    assert provider.generate_text(system="s", user="u", max_tokens=5) == "ok"
    assert len(sleeps) == 1

    def slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    provider, rec, sleeps = make_provider(slow)
    with pytest.raises(LLMTimeoutError) as info:
        provider.generate_text(system="s", user="u", max_tokens=5)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None
    assert len(rec.requests) == 1
    assert sleeps == []


def test_remaining_tokens_header_is_logged_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    ok = reply("ok")
    ok.headers["x-ratelimit-remaining-tokens"] = "1999880"
    provider, _, _ = make_provider(sequence(ok))
    with caplog.at_level(logging.DEBUG, logger="fhc_api.llm.openai"):
        provider.generate_text(system="s", user="u", max_tokens=5)
    assert "x-ratelimit-remaining-tokens=1999880" in caplog.text
    assert KEY not in caplog.text


def test_errors_and_logs_never_contain_the_key_or_the_prompt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    prompt = "PROMPT-MARKER-should-stay-private"
    factories: list[Callable[[], httpx2.Response]] = [
        lambda: error(401, "invalid_api_key", message=f"Incorrect API key provided: {KEY}"),
        lambda: error(400, None, message=f"bad request {prompt}"),
        lambda: error(429, "rate_limit_exceeded", message=KEY),
        lambda: error(429, KEY),  # a code that is not an identifier is not echoed
        lambda: error(400, "sk-proj-leakmarker"),
        lambda: httpx2.Response(500, text=f"<html>{KEY}</html>"),
    ]
    messages: list[str] = []
    with caplog.at_level(logging.DEBUG):
        for factory in factories:

            def handler(
                _request: httpx2.Request, f: Callable[[], httpx2.Response] = factory
            ) -> httpx2.Response:
                return f()

            provider, _, _ = make_provider(handler)
            with pytest.raises(LLMError) as info:
                provider.generate_structured(system=prompt, user=prompt, schema=Sample)
            messages.append(str(info.value))
    for text in [*messages, caplog.text]:
        assert KEY not in text
        assert "leakmarker" not in text.lower()
        assert prompt not in text


# -- configuration ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"api_key": ""}, "API key"),
        ({"api_key": "short"}, "API key"),
        ({"api_key": "sk-has a space-0123456789"}, "API key"),
        ({"model": " "}, "model"),
        ({"model": "gpt/../x"}, "model"),
        ({"timeout_s": 0}, "timeout"),
        ({"reasoning_effort": "max"}, "reasoning effort"),
        ({"base_url": "http://api.openai.com"}, "https"),
        ({"base_url": "https://u:p@api.openai.com"}, "credentials"),
        ({"daily_token_budget": 0}, "budget"),
        ({"daily_token_budget": 100, "max_output_tokens": 101}, "budget"),
        ({"total_timeout_s": 0}, "total timeout"),
    ],
)
def test_invalid_configuration_is_rejected_without_echoing_secrets(
    kwargs: dict[str, Any], match: str
) -> None:
    args: dict[str, Any] = {"api_key": KEY, "model": MODEL, "timeout_s": 1, **kwargs}
    with pytest.raises(LLMConfigError, match=match) as info:
        OpenAIProvider(**args)
    assert "has a space" not in str(info.value)
    assert "u:p" not in str(info.value)


@pytest.mark.parametrize("model", [KEY, "sk-proj-abcdefghijklmnop", "SK-abc"])
def test_model_name_that_looks_like_a_key_is_rejected(model: str) -> None:
    with pytest.raises(LLMConfigError, match="looks like an API key") as info:
        OpenAIProvider(KEY, model, timeout_s=1)
    assert model not in str(info.value)
    assert "abcdefghijklmnop" not in str(info.value)


def test_http_base_url_is_allowed_for_localhost() -> None:
    provider = OpenAIProvider(KEY, MODEL, timeout_s=1, base_url="http://127.0.0.1:8080")
    assert provider.base_url == "http://127.0.0.1:8080"


# -- budget -----------------------------------------------------------------------------------


def test_daily_budget_refuses_calls_and_resets_at_utc_midnight() -> None:
    now = [datetime(2026, 10, 13, 23, 0, tzinfo=UTC)]
    provider, rec, _ = make_provider(
        lambda _r: reply("ok", input_tokens=80, output_tokens=40),
        daily_token_budget=300,
        max_output_tokens=10,
        utc_now=lambda: now[0],
    )

    # Each call reserves about 70 tokens (estimated input + max_tokens) and uses 120.
    provider.generate_text(system="s", user="u", max_tokens=5)  # 120
    provider.generate_text(system="s", user="u", max_tokens=5)  # 240
    assert provider.tokens_used_today == 240
    with pytest.raises(LLMError, match="daily token budget reached"):
        provider.generate_text(system="s", user="u", max_tokens=5)
    assert len(rec.requests) == 2

    now[0] = datetime(2026, 10, 14, 0, 0, 1, tzinfo=UTC)
    assert provider.tokens_used_today == 0
    assert provider.generate_text(system="s", user="u", max_tokens=5) == "ok"
    assert provider.total_usage.total_tokens == 360


def test_budget_reservation_blocks_a_concurrent_overshoot() -> None:
    entered = threading.Event()
    release = threading.Event()

    def handler(_request: httpx2.Request) -> httpx2.Response:
        entered.set()
        assert release.wait(5)
        return reply("ok", input_tokens=50, output_tokens=10)

    provider, rec, _ = make_provider(handler, daily_token_budget=6000, max_output_tokens=4000)
    results: list[str] = []
    worker = threading.Thread(
        target=lambda: results.append(provider.generate_text(system="s", user="u", max_tokens=4000))
    )
    worker.start()
    try:
        assert entered.wait(5)
        # The call in flight holds ~4,070 tokens although nothing has been used yet.
        assert provider.tokens_used_today == 0
        assert provider.tokens_available_today < 2000
        with pytest.raises(LLMError, match="daily token budget reached"):
            provider.generate_text(system="s", user="u", max_tokens=4000)
    finally:
        release.set()
        worker.join(5)
    assert results == ["ok"]
    assert provider.tokens_used_today == 60
    assert provider.tokens_available_today == 5940  # reservation settled to actual usage
    assert provider.generate_text(system="s", user="u", max_tokens=4000) == "ok"
    assert len(rec.requests) == 2


def test_failed_call_releases_its_reservation() -> None:
    provider, _, _ = make_provider(sequence(error(400, None)), daily_token_budget=5000)
    with pytest.raises(LLMError):
        provider.generate_structured(system="s", user="u", schema=Sample)
    assert provider.tokens_available_today == 5000


def test_health_reports_budget_exhaustion_without_a_request() -> None:
    provider, rec, _ = make_provider(
        sequence(reply("ok", input_tokens=100, output_tokens=20)),
        daily_token_budget=4000,
        max_output_tokens=4000,
    )
    provider.generate_text(system="s", user="u", max_tokens=5)

    health = provider.health()

    assert health.status == "error"
    assert "daily token budget reached" in health.message
    assert len(rec.requests) == 1  # no GET /v1/models


# -- PII masking --------------------------------------------------------------------------------


def test_pii_is_masked_in_instructions_and_input() -> None:
    provider, rec, _ = make_provider(sequence(reply('{"city": "x", "year": 1}')))
    provider.generate_structured(
        system="Contact admin@example.com",
        user="Ara: +90 532 123 45 67, TC 10000000146, mail info@hack.org.tr",
        schema=Sample,
    )
    body = json.dumps(rec.bodies[0], ensure_ascii=False)
    for secret in ("admin@example.com", "532 123 45 67", "10000000146", "info@hack.org.tr"):
        assert secret not in body
    assert rec.bodies[0]["instructions"] == "Contact [email]"
    assert rec.bodies[0]["input"][0]["content"] == "Ara: [phone], TC [tc_kimlik], mail [email]"


def test_repair_turn_is_masked() -> None:
    provider, rec, _ = make_provider(
        sequence(
            reply('{"city": "info@hack.org.tr", "note": "+90 532 123 45 67"}'),
            reply('{"city": "x", "year": 1}'),
        )
    )
    provider.generate_structured(system="s", user="u", schema=Sample)

    repair = json.dumps(rec.bodies[1], ensure_ascii=False)
    assert "info@hack.org.tr" not in repair
    assert "532 123 45 67" not in repair
    assert rec.bodies[1]["input"][1]["content"] == '{"city": "[email]", "note": "[phone]"}'


# -- health -----------------------------------------------------------------------------------


def test_health_ok_uses_models_endpoint() -> None:
    provider, rec, _ = make_provider(
        sequence(httpx2.Response(200, json={"id": MODEL, "object": "model"}))
    )
    health = provider.health()
    assert health.status == "ok"
    assert health.installed_models == [MODEL]
    (request,) = rec.requests
    assert request.method == "GET"
    assert str(request.url) == f"{BASE}/v1/models/{MODEL}"


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (error(404, "model_not_found"), "model_missing"),
        (error(401, "invalid_api_key", message=KEY), "error"),
        (error(503, None), "not_running"),
    ],
)
def test_health_maps_errors(response: httpx2.Response, status: str) -> None:
    provider, _, _ = make_provider(sequence(response))
    health = provider.health()
    assert health.status == status
    assert KEY not in health.message


def test_health_connect_error_is_not_running() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    provider, _, _ = make_provider(handler)
    assert provider.health().status == "not_running"
