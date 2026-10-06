"""The admin bot's background thread: getMe, then a loop of outbox scans and getUpdates
long polls. It never raises into the API: every failure is logged (no secrets, no
personal data), shown by `GET /admin-bot/status`, and followed by a backoff.

Shutdown: `stop()` sets an event and joins the thread for at most
`POLL_TIMEOUT_S + DEFAULT_TIMEOUT_S + 5` = 25 s. Backoff and pacing waits end at once;
loops over updates, sends and edits check the event between calls, so the thread stops
after the call in progress: a long poll (HTTP timeout 20 s), another Bot API call (10 s), a
pool checkout (10 s) or a statement (15 s statement_timeout). Usually that is well under a
second. If the join times out, a warning is logged and the daemon thread exits on its
own. No database connection is held during a Telegram call.
"""

import threading
import time
from datetime import UTC, datetime

import psycopg
from fastapi import HTTPException
from pydantic import ValidationError

from fhc_api.admin_bot import store
from fhc_api.admin_bot.context import BotContext, logger
from fhc_api.admin_bot.handlers import Handlers
from fhc_api.admin_bot.outbox import Outbox
from fhc_api.admin_bot.settings import AdminBotConfig
from fhc_api.db import ConnFactory
from fhc_api.telegram.client import (
    DEFAULT_TIMEOUT_S,
    TelegramAPIError,
    TelegramClient,
    TelegramError,
    TelegramUpdate,
)
from fhc_api.web.revalidate import Revalidator

POLL_TIMEOUT_S = 10
ALLOWED_UPDATES = ["message", "callback_query"]
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 300.0
INVALID_TOKEN_BACKOFF_S = 600.0
# An update that keeps failing with a connection error is skipped after this many tries.
MAX_UPDATE_ATTEMPTS = 5
# admin_shutdown, crash_shutdown, cannot_connect_now
_SHUTDOWN_STATES = frozenset({"57P01", "57P02", "57P03"})


def is_connection_error(exc: psycopg.OperationalError) -> bool:
    """The database is unreachable (connection lost or refused, pool timeout, server
    shutdown), as opposed to a statement-level error such as a cancelled query."""
    sqlstate = exc.sqlstate
    return sqlstate is None or sqlstate.startswith("08") or sqlstate in _SHUTDOWN_STATES


def describe_error(exc: BaseException) -> str:
    """A secret- and data-free description. Telegram errors never contain the token;
    database and validation messages can contain row values, so only their class is kept."""
    if isinstance(exc, TelegramAPIError):
        if exc.error_code in (401, 404) and exc.method == "getMe":
            return "Telegram rejected TELEGRAM_ADMIN_BOT_TOKEN (getMe unauthorized)"
        if exc.error_code == 409:
            return (
                f"{exc} (another process is polling this bot, or a webhook is set; "
                "only one admin API may run with the bot enabled)"
            )
        return str(exc)
    if isinstance(exc, TelegramError):
        return str(exc)
    if isinstance(exc, psycopg.Error):
        return f"database error ({type(exc).__name__}, sqlstate={exc.sqlstate})"
    return f"internal error ({type(exc).__name__})"


class AdminBotRunner:
    def __init__(
        self,
        config: AdminBotConfig,
        client: TelegramClient,
        open_conn: ConnFactory,
        revalidator: Revalidator,
    ) -> None:
        self._stop = threading.Event()
        self._scan_requested = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._client = client
        self._open_conn = open_conn
        ctx = BotContext(
            config=config,
            client=client,
            open_conn=open_conn,
            revalidator=revalidator,
            request_scan=self._scan_requested.set,
            sleep=self._stop.wait,
            stopping=self._stop.is_set,
        )
        self._scan_interval_s = config.scan_interval_s
        self._outbox = Outbox(ctx)
        self._handlers = Handlers(ctx)
        self._bot_id: int | None = None
        self._offset: int | None = None
        # Connection-error tries of the update at the head of the queue (update id -> tries).
        self._attempts: dict[int, int] = {}
        self._next_scan = 0.0
        # Status (read by the API thread under the lock).
        self.bot_username: str | None = None
        self.started = False
        self.healthy = False
        self.last_poll_at: datetime | None = None
        self.last_scan_at: datetime | None = None
        self.last_error: str | None = None
        self.last_error_at: datetime | None = None

    # --- lifecycle ---------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="fhc-admin-bot", daemon=True)
        self.started = True
        self._thread.start()
        logger.info("admin bot started")

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is None:
            return
        thread.join(timeout=POLL_TIMEOUT_S + DEFAULT_TIMEOUT_S + 5)
        if thread.is_alive():  # pragma: no cover - only when Telegram hangs past the timeout
            logger.warning("admin bot thread did not stop in time; it exits after its poll")
        else:
            logger.info("admin bot stopped")
        self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "bot_username": self.bot_username,
                "started": self.started,
                "running": self.running,
                "healthy": self.healthy,
                "last_poll_at": self.last_poll_at,
                "last_scan_at": self.last_scan_at,
                "last_error": self.last_error,
                "last_error_at": self.last_error_at,
            }

    # --- units of work (the loop calls these; tests drive them directly) ----------------

    def identify(self) -> None:
        me = self._client.get_me()
        with self._open_conn() as conn:
            offset = store.load_offset(conn, me.id)
        with self._lock:
            self._bot_id, self._offset = me.id, offset
            self.bot_username = me.username

    def scan(self) -> int:
        sent = self._outbox.scan()
        with self._lock:
            self.last_scan_at = datetime.now(UTC)
        return sent

    def poll_once(self, timeout_s: int) -> int:
        """One getUpdates call; handles and confirms each update in order. A database
        outage stops the batch before the failing update, so it is retried later (at most
        MAX_UPDATE_ATTEMPTS times).

        The handler's transaction commits before the offset is saved. A crash in between
        re-processes that update after a restart; that is harmless (the press finds its
        message already resolved, a reply finds its prompt used up), except that a Request
        changes / Reject confirm press can send a second reason prompt."""
        if self._bot_id is None:
            self.identify()
        updates = self._client.get_updates(
            offset=self._offset, timeout_s=timeout_s, allowed_updates=ALLOWED_UPDATES
        )
        with self._lock:
            self.last_poll_at = datetime.now(UTC)
        handled = 0
        for update in updates:
            if self._stop.is_set():
                break
            self._handle(update)
            self._attempts.pop(update.update_id, None)
            self._offset = update.update_id + 1
            with self._open_conn() as conn:
                store.save_offset(conn, self._bot_id or 0, self._offset)
            handled += 1
        return handled

    def _handle(self, update: TelegramUpdate) -> None:
        try:
            self._handlers.handle(update)
        except psycopg.OperationalError as exc:
            attempts = self._attempts.get(update.update_id, 0) + 1
            if is_connection_error(exc) and attempts < MAX_UPDATE_ATTEMPTS:
                # Database unreachable: do not confirm; retried after the backoff.
                self._attempts = {update.update_id: attempts}
                raise
            self._record_error(exc, f"skipping update {update.update_id}")
        except (TelegramError, psycopg.Error, HTTPException, ValidationError, ValueError) as exc:
            # A bad update must not block the queue: log and move on.
            self._record_error(exc, "handling an update")
        except Exception as exc:
            logger.exception("admin bot: unexpected error while handling an update")
            self._record_error(exc, None)

    # --- loop --------------------------------------------------------------------------

    def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            try:
                if self._bot_id is None:
                    self.identify()
                if self._scan_requested.is_set() or time.monotonic() >= self._next_scan:
                    self._scan_requested.clear()
                    self._next_scan = time.monotonic() + self._scan_interval_s
                    self.scan()
                self.poll_once(self._poll_timeout())
            except Exception as exc:
                failures += 1
                delay = self._backoff(exc, failures)
                self._record_error(exc, f"retrying in {delay:.0f} s")
                self._stop.wait(delay)
                continue
            failures = 0
            with self._lock:
                self.healthy = True

    def _poll_timeout(self) -> int:
        if self._scan_requested.is_set():
            return 0
        until_scan = self._next_scan - time.monotonic()
        return max(1, min(POLL_TIMEOUT_S, int(until_scan)))

    @staticmethod
    def _backoff(exc: BaseException, failures: int) -> float:
        if isinstance(exc, TelegramAPIError):
            if exc.retry_after is not None:
                return float(min(max(exc.retry_after, 1), BACKOFF_MAX_S))
            if exc.method == "getMe" and exc.error_code in (401, 404):
                return INVALID_TOKEN_BACKOFF_S
        return float(min(BACKOFF_BASE_S ** min(failures, 9), BACKOFF_MAX_S))

    def _record_error(self, exc: BaseException, context: str | None) -> None:
        message = describe_error(exc)
        if context:
            logger.warning("admin bot: %s; %s", message, context)
        with self._lock:
            self.healthy = False
            self.last_error = message
            self.last_error_at = datetime.now(UTC)
