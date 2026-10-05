"""`GET /telegram/check`. No authentication here; the application adds it globally."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from fhc_api.telegram.check import TelegramCheckResult, run_telegram_check
from fhc_api.telegram.client import TelegramClient


def build_telegram_router(
    get_client: Callable[[], TelegramClient | None],
    channel_id: int | str | None,
    *,
    invalid_token_format: bool = False,
) -> APIRouter:
    """`get_client` returns None when no bot token is configured, or when the configured
    token could not be used (`invalid_token_format=True`; the check then reports it)."""
    router = APIRouter(tags=["telegram"])

    @router.get(
        "/telegram/check", operation_id="telegram_check", response_model=TelegramCheckResult
    )
    def telegram_check(
        client: Annotated[TelegramClient | None, Depends(get_client)],
    ) -> TelegramCheckResult:
        return run_telegram_check(client, channel_id, invalid_token_format=invalid_token_format)

    return router
