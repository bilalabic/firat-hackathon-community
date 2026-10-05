"""Best-effort on-demand revalidation of the public site (PUBLIC_WEB §2).

`POST {WEB_BASE_URL}/api/revalidate` with `Authorization: Bearer <WEB_REVALIDATE_SECRET>`
and `{"tags": [...]}`. A failure is logged and swallowed: the public site falls back
to its `cacheLife` expiry, so a publish never fails because the site is unreachable.
The secret never appears in logs (only the status code or the exception class).
"""

import logging
from typing import Annotated, Protocol

import httpx2
from fastapi import Depends, Request

from fhc_api.config import Settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0


def event_tags(slug: str) -> list[str]:
    return ["events", f"event:{slug}"]


class Revalidator(Protocol):
    def revalidate(self, tags: list[str]) -> None: ...


def get_revalidator(request: Request) -> Revalidator:
    revalidator: Revalidator = request.app.state.revalidator
    return revalidator


RevalidatorDep = Annotated[Revalidator, Depends(get_revalidator)]


class WebRevalidator:
    def __init__(self, settings: Settings, transport: httpx2.BaseTransport | None = None) -> None:
        self._endpoint = (
            f"{str(settings.WEB_BASE_URL).rstrip('/')}/api/revalidate"
            if settings.WEB_BASE_URL
            else None
        )
        self._secret = settings.WEB_REVALIDATE_SECRET
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return self._endpoint is not None and self._secret is not None

    def revalidate(self, tags: list[str]) -> None:
        if self._endpoint is None or self._secret is None:
            logger.debug("web revalidation disabled (WEB_BASE_URL or secret not set)")
            return
        try:
            with httpx2.Client(
                transport=self._transport,
                timeout=httpx2.Timeout(TIMEOUT_SECONDS),
                follow_redirects=False,
                # The bearer secret must never go through an environment proxy.
                trust_env=False,
            ) as client:
                response = client.post(
                    self._endpoint,
                    json={"tags": tags},
                    headers={"Authorization": f"Bearer {self._secret.get_secret_value()}"},
                )
        except httpx2.HTTPError as exc:
            logger.warning("web revalidation failed: %s", type(exc).__name__)
            return
        if response.is_success:
            logger.info("web revalidation ok for %d tag(s)", len(tags))
        else:
            logger.warning("web revalidation failed: HTTP %d", response.status_code)
