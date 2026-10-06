"""What the app factory wires: configuration check, the runner's lifecycle and status.

Disabled by default. When disabled or misconfigured, nothing starts and no Telegram call
is made; the API and its other routes are unaffected (V1_1B acceptance 1)."""

from datetime import datetime
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from fhc_api.admin_bot import store
from fhc_api.admin_bot.context import logger
from fhc_api.admin_bot.runner import AdminBotRunner
from fhc_api.admin_bot.settings import (
    AdminBotConfig,
    AdminBotConfigError,
    is_enabled,
    load_config,
)
from fhc_api.config import Settings
from fhc_api.db import ConnFactory
from fhc_api.telegram.client import TelegramClient, TelegramConfigError
from fhc_api.web.revalidate import Revalidator

AdminBotState = Literal["disabled", "config_error", "stopped", "starting", "running", "error"]


class AdminBotStatus(BaseModel):
    enabled: bool = Field(description="TELEGRAM_ADMIN_ENABLED")
    state: AdminBotState = Field(
        description="disabled (default), config_error (enabled but not started), stopped "
        "(not started yet or shut down), starting, running, error (retrying with backoff)"
    )
    running: bool = Field(description="The background thread is alive")
    config_error: str | None = None
    bot_username: str | None = None
    allowlist_size: int
    max_press_age_hours: float | None
    scan_interval_seconds: float | None
    last_poll_at: datetime | None = None
    last_scan_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    pending_notifications: int | None = Field(
        description="Sent messages still waiting for a decision; null when the DB is down"
    )
    pending_replies: int | None = Field(description="Open reason prompts")


class AdminBot:
    def __init__(
        self,
        settings: Settings,
        open_conn: ConnFactory,
        revalidator: Revalidator,
        *,
        client: TelegramClient | None = None,
    ) -> None:
        self.enabled = is_enabled(settings)
        self.config: AdminBotConfig | None = None
        self.config_error: str | None = None
        self.runner: AdminBotRunner | None = None
        self._owned_client: TelegramClient | None = None
        if not self.enabled:
            return
        try:
            config = load_config(settings)
            if client is None:
                client = self._owned_client = TelegramClient(config.token.get_secret_value())
        except AdminBotConfigError as exc:
            self.config_error = str(exc)
        except TelegramConfigError:
            self.config_error = "TELEGRAM_ADMIN_BOT_TOKEN has an invalid format"
        else:
            self.config = config
            self.runner = AdminBotRunner(config, client, open_conn, revalidator)
            return
        logger.warning("admin bot not started: %s", self.config_error)

    def start(self) -> None:
        if self.runner is not None:
            self.runner.start()

    def stop(self) -> None:
        if self.runner is not None:
            self.runner.stop()

    def close(self) -> None:
        if self._owned_client is not None:
            self._owned_client.close()

    def status(self, open_conn: ConnFactory) -> AdminBotStatus:
        pending: tuple[int, int] | tuple[None, None] = (None, None)
        if self.runner is not None:
            try:
                with open_conn() as conn:
                    pending = store.counts(conn)
            except psycopg.Error:
                pass  # reported as null; /system/db reports the database itself
        runner = self.runner.snapshot() if self.runner is not None else {}
        state: AdminBotState
        if not self.enabled:
            state = "disabled"
        elif self.runner is None:
            state = "config_error"
        elif not runner["running"]:
            state = "stopped"
        elif runner["healthy"]:
            state = "running"
        elif runner["last_error"] is not None:
            state = "error"
        else:
            state = "starting"
        config = self.config
        return AdminBotStatus.model_validate(
            {
                **runner,
                "enabled": self.enabled,
                "state": state,
                "running": bool(runner.get("running", False)),
                "config_error": self.config_error,
                "allowlist_size": len(config.admin_ids) if config else 0,
                "max_press_age_hours": config.max_press_age_h if config else None,
                "scan_interval_seconds": config.scan_interval_s if config else None,
                "pending_notifications": pending[0],
                "pending_replies": pending[1],
            }
        )
