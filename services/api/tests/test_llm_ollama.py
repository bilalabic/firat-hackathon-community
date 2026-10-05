import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel

from fhc_api.llm.ollama import OllamaProvider
from fhc_api.llm.provider import (
    LLMConfigError,
    LLMError,
    LLMModelMissingError,
    LLMOutputError,
    LLMProvider,
    LLMTimeoutError,
    LLMUnavailableError,
)

BASE = "http://127.0.0.1:11434"
MODEL = "qwen3.5:0.8b"


class Sample(BaseModel):
    city: str
    year: int


Handler = Callable[[httpx2.Request], httpx2.Response]


def make_provider(handler: Handler) -> tuple[OllamaProvider, list[dict[str, Any]]]:
    bodies: list[dict[str, Any]] = []

    def recording(request: httpx2.Request) -> httpx2.Response:
        if request.content:
            bodies.append(json.loads(request.content))
        return handler(request)

    client = httpx2.Client(transport=httpx2.MockTransport(recording))
    return OllamaProvider(BASE, MODEL, timeout_s=5, client=client), bodies


def chat_reply(content: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "model": MODEL,
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
        },
    )


def sequence(*responses: httpx2.Response) -> Handler:
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return queue.pop(0)

    return handler


def test_satisfies_protocol() -> None:
    provider: LLMProvider = OllamaProvider(BASE, MODEL, timeout_s=1)
    assert provider.name == "ollama"


def test_generate_structured_success_sends_documented_fields() -> None:
    provider, bodies = make_provider(sequence(chat_reply('{"city": "Elazığ", "year": 2026}')))

    result = provider.generate_structured(system="sys", user="usr", schema=Sample)

    assert result == Sample(city="Elazığ", year=2026)
    (body,) = bodies
    assert body["model"] == MODEL
    assert body["stream"] is False
    assert body["think"] is False
    assert body["options"] == {"temperature": 0.0}
    assert body["format"] == Sample.model_json_schema()
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]


def test_invalid_json_then_repaired() -> None:
    provider, bodies = make_provider(
        sequence(chat_reply('{"city": "Elazığ"}'), chat_reply('{"city": "Elazığ", "year": 2026}'))
    )

    result = provider.generate_structured(system="sys", user="usr", schema=Sample, temperature=0.2)

    assert result.year == 2026
    assert len(bodies) == 2
    retry = bodies[1]["messages"]
    assert [m["role"] for m in retry] == ["system", "user", "assistant", "user"]
    assert retry[2]["content"] == '{"city": "Elazığ"}'
    assert "year: Field required" in retry[3]["content"]
    assert bodies[1]["options"]["temperature"] == 0.2
    assert bodies[1]["format"] == Sample.model_json_schema()


def test_invalid_twice_raises_output_error_after_exactly_one_retry() -> None:
    provider, bodies = make_provider(sequence(chat_reply("not json"), chat_reply("still no")))

    with pytest.raises(LLMOutputError, match="after one repair retry"):
        provider.generate_structured(system="sys", user="usr", schema=Sample)

    assert len(bodies) == 2


def test_repair_prompt_does_not_echo_input_values() -> None:
    secretish = "sk-live-should-not-be-echoed"
    provider, bodies = make_provider(
        sequence(
            chat_reply(json.dumps({"city": "x", "year": secretish})),
            chat_reply('{"city": "x", "year": 1}'),
        )
    )

    provider.generate_structured(system="sys", user="usr", schema=Sample)

    repair_message = bodies[1]["messages"][3]["content"]
    assert secretish not in repair_message
    assert "year:" in repair_message


def test_timeout_raises_timeout_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    provider, _ = make_provider(handler)

    with pytest.raises(LLMTimeoutError) as info:
        provider.generate_structured(system="s", user="u", schema=Sample)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


def test_connection_refused_raises_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    provider, _ = make_provider(handler)

    with pytest.raises(LLMUnavailableError, match="not running"):
        provider.generate_text(system="s", user="u", max_tokens=10)


def test_chat_404_means_model_missing() -> None:
    provider, _ = make_provider(
        sequence(httpx2.Response(404, json={"error": f"model '{MODEL}' not found"}))
    )

    with pytest.raises(LLMModelMissingError):
        provider.generate_structured(system="s", user="u", schema=Sample)


def test_server_error_is_reported_with_truncated_detail() -> None:
    provider, _ = make_provider(sequence(httpx2.Response(500, json={"error": "x" * 1000})))

    with pytest.raises(LLMError) as info:
        provider.generate_text(system="s", user="u", max_tokens=10)
    assert "HTTP 500" in str(info.value)
    assert len(str(info.value)) < 300


def test_generate_text_sets_num_predict_and_no_format() -> None:
    provider, bodies = make_provider(sequence(chat_reply("Merhaba")))

    assert provider.generate_text(system="s", user="u", max_tokens=42) == "Merhaba"
    assert bodies[0]["options"] == {"temperature": 0.0, "num_predict": 42}
    assert "format" not in bodies[0]


def tags(*names: str) -> httpx2.Response:
    return httpx2.Response(200, json={"models": [{"name": n, "model": n} for n in names]})


def test_health_ok() -> None:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(f"{request.method} {request.url}")
        return tags("gemma4:e2b-it-qat", MODEL)

    provider, _ = make_provider(handler)

    health = provider.health()

    assert requested == [f"GET {BASE}/api/tags"]
    assert health.status == "ok"
    assert health.installed_models == ["gemma4:e2b-it-qat", MODEL]
    assert health.configured_model == MODEL


def test_health_latest_tag_is_implicit() -> None:
    client = httpx2.Client(transport=httpx2.MockTransport(lambda r: tags("qwen3:latest")))
    provider = OllamaProvider(BASE, "qwen3", timeout_s=1, client=client)

    assert provider.health().status == "ok"


def test_health_model_missing() -> None:
    provider, _ = make_provider(sequence(tags("gemma4:e2b-it-qat")))

    health = provider.health()

    assert health.status == "model_missing"
    assert f"ollama pull {MODEL}" in health.message


def test_health_not_running() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("[WinError 10061] refused", request=request)

    provider, _ = make_provider(handler)

    health = provider.health()

    assert health.status == "not_running"
    assert health.installed_models == []


def test_health_timeout_is_not_running() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectTimeout("timed out", request=request)

    provider, _ = make_provider(handler)

    assert provider.health().status == "not_running"


def test_health_unexpected_payload_is_error() -> None:
    provider, _ = make_provider(sequence(httpx2.Response(200, json={"nope": 1})))

    assert provider.health().status == "error"


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:11434", "http://localhost:11434/", "http://[::1]:11434", "http://127.0.0.2"],
)
def test_local_base_urls_accepted(url: str) -> None:
    assert OllamaProvider(url, MODEL, timeout_s=1).base_url.startswith("http://")


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.10:11434",
        "http://example.com:11434",
        "http://localhost.example.com",
        "http://0.0.0.0:11434",
        "ftp://127.0.0.1",
        "127.0.0.1:11434",
        "http://user:pw@127.0.0.1:11434",
    ],
)
def test_unsafe_base_urls_rejected(url: str) -> None:
    with pytest.raises(LLMConfigError):
        OllamaProvider(url, MODEL, timeout_s=1)


def test_remote_base_url_allowed_explicitly() -> None:
    provider = OllamaProvider("http://192.168.1.10:11434", MODEL, timeout_s=1, allow_remote=True)
    assert provider.base_url == "http://192.168.1.10:11434"


@pytest.mark.parametrize(("model", "timeout"), [("", 1.0), ("m", 0.0)])
def test_invalid_config_rejected(model: str, timeout: float) -> None:
    with pytest.raises(LLMConfigError):
        OllamaProvider(BASE, model, timeout_s=timeout)


def test_protocol_error_is_generic_error_not_not_running() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.RemoteProtocolError("garbage", request=request)

    provider, _ = make_provider(handler)

    health = provider.health()
    assert health.status == "error"
    assert "RemoteProtocolError" in health.message
