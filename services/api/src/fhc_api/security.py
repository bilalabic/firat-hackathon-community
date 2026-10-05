"""Bearer-token check for every route except `/health` (SECURITY §4)."""

import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from fhc_api.config import Settings

_bearer = HTTPBearer(auto_error=False, description="ADMIN_API_TOKEN from services/api/.env")


def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    settings: Settings = request.app.state.settings
    expected = settings.ADMIN_API_TOKEN.get_secret_value().encode()
    supplied = credentials.credentials.encode() if credentials else b""
    # Constant-time comparison: it does not stop at the first differing byte.
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
