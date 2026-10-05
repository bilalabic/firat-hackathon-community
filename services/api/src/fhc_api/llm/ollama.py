"""Ollama provider over the native REST API (https://docs.ollama.com/api).

- `POST /api/chat` with `stream: false`, `think: false`, `options.temperature` and, for structured
  output, `format` = the Pydantic JSON Schema.
- `GET /api/tags` lists installed models for `health()`.

Configuration is injected through the constructor; this module reads no environment variables.
"""

import ipaddress
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

import httpx2
from pydantic import ValidationError

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

_LOCAL_HOSTNAMES = frozenset({"localhost"})
_MAX_ERROR_DETAIL = 200
_MAX_ECHOED_OUTPUT = 2000
_MAX_REPORTED_ERRORS = 10

REPAIR_INSTRUCTION = (
    "Your previous reply did not match the required JSON schema. Validation errors:\n"
    "{errors}\n"
    "Reply again with only a JSON object that matches the schema. No prose, no code fences."
)


def _is_local_host(host: str) -> bool:
    if host.lower() in _LOCAL_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validated_base_url(base_url: str, *, allow_remote: bool) -> str:
    parts = urlsplit(base_url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise LLMConfigError("Ollama base URL must be an absolute http(s) URL.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise LLMConfigError("Ollama base URL must not contain credentials, query or fragment.")
    if not allow_remote and not _is_local_host(parts.hostname):
        raise LLMConfigError(
            "Ollama base URL must point to localhost (127.0.0.1, ::1 or localhost). "
            "Pass allow_remote=True to use another host deliberately."
        )
    return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/")


def _same_model(configured: str, installed: str) -> bool:
    # Ollama treats a name without a tag as ":latest".
    def normalize(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    return normalize(configured) == normalize(installed)


def _format_validation_errors(exc: ValidationError) -> str:
    # include_input=False: never echo values back; only field locations and messages.
    lines = [
        f"- {'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
        for err in exc.errors(include_url=False, include_input=False)[:_MAX_REPORTED_ERRORS]
    ]
    return "\n".join(lines)


def _error_detail(response: httpx2.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    detail = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail:
        return f"HTTP {response.status_code}: {detail[:_MAX_ERROR_DETAIL]}"
    return f"HTTP {response.status_code}"


class OllamaProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float,
        client: httpx2.Client | None = None,
        *,
        allow_remote: bool = False,
    ) -> None:
        if not model.strip():
            raise LLMConfigError("Ollama model name must not be empty.")
        if timeout_s <= 0:
            raise LLMConfigError("Ollama timeout must be positive.")
        self._base_url = _validated_base_url(base_url, allow_remote=allow_remote)
        self._model = model.strip()
        self._timeout_s = timeout_s
        self._owns_client = client is None
        # trust_env=False: never route a local model call through an environment proxy.
        self._client = client or httpx2.Client(trust_env=False, follow_redirects=False)

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def __repr__(self) -> str:
        return f"OllamaProvider(base_url={self._base_url!r}, model={self._model!r})"

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

    # -- transport -------------------------------------------------------------------------

    def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        """Send one request and return the decoded JSON body.

        httpx2 exceptions are converted outside the `except` block so that no request/URL
        object is chained onto the error we raise.
        """
        error: LLMError | None = None
        try:
            response = self._client.request(
                method, f"{self._base_url}{path}", json=json, timeout=self._timeout_s
            )
        except httpx2.TimeoutException:
            error = LLMTimeoutError(f"Ollama did not answer within {self._timeout_s:g} s.")
        except httpx2.ConnectError:
            error = LLMUnavailableError(f"Ollama is not running at {self._base_url}.")
        except httpx2.HTTPError as exc:
            error = LLMError(f"Ollama request failed ({type(exc).__name__}).")
        if error is not None:
            raise error

        if response.status_code == 404 and path == "/api/chat":
            raise LLMModelMissingError(f"Model {self._model!r} is not installed in Ollama.")
        if response.status_code != 200:
            raise LLMError(f"Ollama returned an error: {_error_detail(response)}.")
        try:
            return response.json()
        except ValueError:
            error = LLMError("Ollama returned a response that is not JSON.")
        raise error

    def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        format_schema: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> str:
        options: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": options,
        }
        if format_schema is not None:
            body["format"] = format_schema
        payload = self._request("POST", "/api/chat", json=body)
        message = payload.get("message") if isinstance(payload, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise LLMError("Ollama response has no message content.")
        return content

    # -- LLMProvider -----------------------------------------------------------------------

    def generate_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T:
        json_schema = schema.model_json_schema()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        content = self._chat(messages, temperature=temperature, format_schema=json_schema)
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            first_error = exc

        # Exactly one repair retry. The re-ask contains only the model's own previous output
        # and the validation messages (no input values, no configuration, no secrets).
        messages += [
            {"role": "assistant", "content": content[:_MAX_ECHOED_OUTPUT]},
            {
                "role": "user",
                "content": REPAIR_INSTRUCTION.format(errors=_format_validation_errors(first_error)),
            },
        ]
        content = self._chat(messages, temperature=temperature, format_schema=json_schema)
        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            count = exc.error_count()
        raise LLMOutputError(
            f"Model output did not match schema {schema.__name__} after one repair retry "
            f"({count} validation error(s))."
        )

    def generate_text(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive.")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self._chat(messages, temperature=temperature, max_tokens=max_tokens)

    def health(self) -> ProviderHealth:
        def result(
            status: HealthStatus, message: str, installed: list[str] | None = None
        ) -> ProviderHealth:
            return ProviderHealth(
                provider=self.name,
                status=status,
                configured_model=self._model,
                installed_models=installed or [],
                message=message,
            )

        try:
            payload = self._request("GET", "/api/tags")
        except LLMUnavailableError as exc:
            return result("not_running", str(exc))
        except LLMError as exc:
            return result("error", str(exc))

        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            return result("error", "Ollama /api/tags response has no model list.")
        installed = sorted(
            {m["name"] for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)}
        )
        if any(_same_model(self._model, name) for name in installed):
            return result("ok", f"Ollama is running and {self._model!r} is installed.", installed)
        return result(
            "model_missing",
            f"Ollama is running but {self._model!r} is not installed. "
            f"Run: ollama pull {self._model}",
            installed,
        )
