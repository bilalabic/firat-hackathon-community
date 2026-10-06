"""`GET /admin-bot/status`. No authentication here; the application adds it globally."""

from collections.abc import Callable

from fastapi import APIRouter

from fhc_api.admin_bot.bot import AdminBot, AdminBotStatus
from fhc_api.db import ConnFactoryDep


def build_admin_bot_router(get_bot: Callable[[], AdminBot]) -> APIRouter:
    router = APIRouter(tags=["admin-bot"])

    @router.get("/admin-bot/status", operation_id="admin_bot_status", response_model=AdminBotStatus)
    def admin_bot_status(open_conn: ConnFactoryDep) -> AdminBotStatus:
        return get_bot().status(open_conn)

    return router
