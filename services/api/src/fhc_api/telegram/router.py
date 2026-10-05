"""`GET /telegram/check`. No authentication here; the application adds it globally."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends

from fhc_api.telegram.check import TelegramCheckResult, run_telegram_check
from fhc_api.telegram.client import TelegramClient


def build_telegram_router(
    get_client: Callable[[], TelegramClient | None], channel_id: int | str | None
) -> APIRouter:
    """`get_client` returns None when no bot token is configured."""
    router = APIRouter(tags=["telegram"])

    @router.get(
        "/telegram/check", operation_id="telegram_check", response_model=TelegramCheckResult
    )
    def telegram_check(
        client: Annotated[TelegramClient | None, Depends(get_client)],
    ) -> TelegramCheckResult:
        return run_telegram_check(client, channel_id)

    return router
