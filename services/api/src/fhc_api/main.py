"""App factory. Run with `uvicorn fhc_api.main:create_app_from_env --factory`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fhc_api import __doc__ as description
from fhc_api.common.errors import error_responses, install_error_handlers
from fhc_api.community.router import router as community_router
from fhc_api.config import Settings
from fhc_api.db import create_pool
from fhc_api.events.router import router as events_router
from fhc_api.llm.ollama import OllamaProvider
from fhc_api.llm.provider import LLMProvider
from fhc_api.llm.router import build_llm_router
from fhc_api.overview.router import router as overview_router
from fhc_api.review.router import router as review_router
from fhc_api.review.signals import UrlChecker, check_url_reachable
from fhc_api.security import require_token
from fhc_api.sources.router import event_sources_router
from fhc_api.sources.router import router as sources_router
from fhc_api.system.router import router as system_router
from fhc_api.telegram.client import TelegramClient
from fhc_api.telegram.router import build_telegram_router
from fhc_api.web.revalidate import Revalidator, WebRevalidator

logger = logging.getLogger(__name__)


class HealthOut(BaseModel):
    status: str
    service: str


def create_app(
    settings: Settings,
    *,
    revalidator: Revalidator | None = None,
    url_checker: UrlChecker | None = None,
    llm_provider: LLMProvider | None = None,
    telegram_client: TelegramClient | None = None,
) -> FastAPI:
    pool = create_pool(settings.DATABASE_URL.get_secret_value())
    # Integration clients are created once per app and closed on shutdown.
    # Injected instances (tests) are owned and closed by the caller.
    own_llm = llm_provider is None
    llm: LLMProvider = llm_provider or OllamaProvider(
        settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL, settings.OLLAMA_TIMEOUT_S
    )
    own_telegram = telegram_client is None
    token = settings.TELEGRAM_BOT_TOKEN.get_secret_value() if settings.TELEGRAM_BOT_TOKEN else ""
    telegram = telegram_client or (TelegramClient(token) if token else None)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # wait=False: the API starts (and /health answers) even when the DB is down;
        # DB-backed routes then return 503 and /system/db reports it.
        pool.open(wait=False)
        revalidation = settings.WEB_BASE_URL and settings.WEB_REVALIDATE_SECRET
        logger.info("web revalidation %s", "enabled" if revalidation else "disabled")
        try:
            yield
        finally:
            pool.close()
            if own_llm and isinstance(llm, OllamaProvider):
                llm.close()
            if own_telegram and telegram is not None:
                telegram.close()

    app = FastAPI(
        title="FHC Admin API",
        description=description or "",
        version="0.1.0",
        lifespan=lifespan,
        # The schema is served only to authenticated callers (below); no Swagger UI.
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.pool = pool
    app.state.revalidator = revalidator or WebRevalidator(settings)
    app.state.url_checker = url_checker or check_url_reachable

    # Rejects DNS-rebinding requests (foreign Host header) with 400. No CORS middleware:
    # the only caller is the admin app's server side, never a browser.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
    install_error_handlers(app)

    @app.get("/health", operation_id="health", response_model=HealthOut, tags=["system"])
    def health() -> HealthOut:
        return HealthOut(status="ok", service="api")

    protected = APIRouter(dependencies=[Depends(require_token)], responses=error_responses(401))
    for router in (
        overview_router,
        events_router,
        review_router,
        event_sources_router,
        sources_router,
        community_router,
        system_router,
        build_llm_router(lambda: llm),
        build_telegram_router(lambda: telegram, settings.TELEGRAM_CHANNEL_ID),
    ):
        protected.include_router(router)

    @protected.get("/openapi.json", include_in_schema=False)
    def openapi_schema() -> dict[str, Any]:
        return app.openapi()

    app.include_router(protected)
    return app


def create_app_from_env() -> FastAPI:
    # Required values come from the environment or services/api/.env, not from kwargs.
    return create_app(Settings())  # type: ignore[call-arg]
