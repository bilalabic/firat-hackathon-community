"""`GET /llm/check`: provider health plus one schema-constrained test call (AI_ARCHITECTURE §5).

No authentication here; the application adds it globally.
"""

import time
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from fhc_api.llm.provider import LLMError, LLMProvider, ProviderHealth


class LLMCheckSample(BaseModel):
    """Fixed 3-field schema for the connectivity test."""

    event_name: str = Field(max_length=100)
    city: str = Field(max_length=50)
    year: int = Field(ge=2000, le=2100)


CHECK_SYSTEM_PROMPT = (
    "You extract facts from a short sentence. Return only JSON that matches the schema."
)
CHECK_USER_PROMPT = "Sentence: Fırat Hackathon 2026 Elazığ'da yapılacak."


class LLMCheckTest(BaseModel):
    ok: bool
    latency_ms: int
    output: LLMCheckSample | None = None
    error: str | None = None


class LLMCheckResponse(BaseModel):
    health: ProviderHealth
    test: LLMCheckTest | None = None


def run_llm_check(provider: LLMProvider) -> LLMCheckResponse:
    health = provider.health()
    if health.status != "ok":
        return LLMCheckResponse(health=health)
    started = time.perf_counter()
    try:
        output = provider.generate_structured(
            system=CHECK_SYSTEM_PROMPT, user=CHECK_USER_PROMPT, schema=LLMCheckSample
        )
    except LLMError as exc:
        test = LLMCheckTest(ok=False, latency_ms=_elapsed_ms(started), error=str(exc))
    else:
        test = LLMCheckTest(ok=True, latency_ms=_elapsed_ms(started), output=output)
    return LLMCheckResponse(health=health, test=test)


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def build_llm_router(get_provider: Callable[[], LLMProvider]) -> APIRouter:
    router = APIRouter(tags=["llm"])

    @router.get("/llm/check", operation_id="llm_check", response_model=LLMCheckResponse)
    def llm_check(
        provider: Annotated[LLMProvider, Depends(get_provider)],
    ) -> LLMCheckResponse:
        return run_llm_check(provider)

    return router
