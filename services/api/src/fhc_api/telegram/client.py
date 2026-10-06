"""Minimal Telegram Bot API client over httpx2 (D-12, https://core.telegram.org/bots/api).

Requests go to `https://api.telegram.org/bot<token>/METHOD`, so the request URL contains the
token. To keep it out of errors, reprs and logs:

- httpx2 exceptions are converted into our own errors outside the `except` block, so no
  httpx2 request/URL object is attached or chained (`__cause__` and `__context__` stay empty);
- `__repr__` never shows the token;
- a logging filter on the `httpx2` logger (which logs every request URL at INFO) redacts
  `bot<token>` path segments.

The read methods serve the M6 channel check; the update, send and edit methods serve the
V1.1b admin bot (`fhc_api.admin_bot`).
"""

import logging
import re
from typing import Any, TypeVar

import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_TOKEN_RE = re.compile(r"[0-9]{1,20}:[A-Za-z0-9_-]{20,100}")
_URL_TOKEN_RE = re.compile(r"/bot[0-9]{1,20}:[A-Za-z0-9_-]+")
_MAX_DESCRIPTION = 300
DEFAULT_TIMEOUT_S = 10.0
# answerCallbackQuery `text`: 0-200 characters (Bot API 10.3).
ANSWER_TEXT_MAX = 200

M = TypeVar("M", bound=BaseModel)
logger = logging.getLogger(__name__)


class _TelegramModel(BaseModel):
    # Telegram adds fields over time; we keep only what we use.
    model_config = ConfigDict(extra="ignore", frozen=True)


class TelegramUser(_TelegramModel):
    id: int
    is_bot: bool
    first_name: str
    username: str | None = None


class TelegramChat(_TelegramModel):
    """Subset of `ChatFullInfo`."""

    id: int
    type: str  # "private" | "group" | "supergroup" | "channel"
    title: str | None = None
    username: str | None = None


class TelegramChatMember(_TelegramModel):
    """Flattened subset of the `ChatMember` union (discriminated by `status`)."""

    status: str  # "creator" | "administrator" | "member" | "restricted" | "left" | "kicked"
    user: TelegramUser
    # ChatMemberAdministrator; `can_post_messages` and `can_edit_messages` are "channels only".
    can_post_messages: bool | None = None
    can_edit_messages: bool | None = None
    can_delete_messages: bool | None = None
    # Rights V1 does not need; the check reports them as excess (least privilege).
    can_change_info: bool | None = None
    can_invite_users: bool | None = None
    can_restrict_members: bool | None = None
    can_promote_members: bool | None = None
    can_manage_video_chats: bool | None = None
    can_post_stories: bool | None = None
    can_edit_stories: bool | None = None
    can_delete_stories: bool | None = None
    can_manage_direct_messages: bool | None = None


class TelegramMessage(_TelegramModel):
    """Subset of `Message`. Also parses `InaccessibleMessage` (chat, message_id, date 0)."""

    message_id: int
    date: int
    chat: TelegramChat
    from_: TelegramUser | None = Field(default=None, alias="from")
    text: str | None = None
    reply_to_message: "TelegramMessage | None" = None


class TelegramCallbackQuery(_TelegramModel):
    id: str
    from_: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    data: str | None = None


class TelegramUpdate(_TelegramModel):
    """Only the update types the admin bot asks for (`allowed_updates`)."""

    update_id: int
    message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = None


class TelegramError(Exception):
    """Base class. Messages never contain the bot token."""


class TelegramConfigError(TelegramError, ValueError):
    """The client was constructed with an invalid token or base URL."""


class TelegramNetworkError(TelegramError):
    """The Bot API could not be reached (DNS, connection, TLS, timeout)."""


class TelegramResponseError(TelegramError):
    """The Bot API answered with something that is not a valid Bot API response."""


class TelegramAPIError(TelegramError):
    """The Bot API answered `{"ok": false, "error_code": ..., "description": ...}`."""

    def __init__(
        self, method: str, error_code: int | None, description: str, retry_after: int | None
    ) -> None:
        self.method = method
        self.error_code = error_code
        self.description = description
        self.retry_after = retry_after
        super().__init__(f"Telegram {method} failed: {error_code} {description}")


def redact_token(text: str) -> str:
    return _URL_TOKEN_RE.sub("/bot<redacted>", text)


class _RedactTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact_token(message)
        if redacted != message:
            record.msg, record.args = redacted, None
        return True


_REDACT_FILTER = _RedactTokenFilter()


def install_log_redaction() -> None:
    """Attach the redaction filter to the `httpx2` logger (idempotent)."""
    httpx_logger = logging.getLogger("httpx2")
    if _REDACT_FILTER not in httpx_logger.filters:
        httpx_logger.addFilter(_REDACT_FILTER)


class TelegramClient:
    def __init__(
        self,
        token: str,
        client: httpx2.Client | None = None,
        base_url: str = "https://api.telegram.org",
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        token = token.strip()
        if not _TOKEN_RE.fullmatch(token):
            # Do not echo the value.
            raise TelegramConfigError(
                "Telegram bot token has an invalid format (expected <id>:<secret>)."
            )
        if not base_url.startswith(("https://", "http://")):
            raise TelegramConfigError("Telegram base URL must be http(s).")
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._owns_client = client is None
        # trust_env=False: the request URL carries the token; never send it via a proxy.
        self._client = client or httpx2.Client(trust_env=False, follow_redirects=False)
        install_log_redaction()

    def __repr__(self) -> str:
        return f"TelegramClient(base_url={self._base_url!r}, token=<redacted>)"

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, method: str, params: dict[str, Any], timeout_s: float | None) -> Any:
        """POST the method; return the `result` of a successful Bot API response."""
        error: TelegramError | None = None
        try:
            response = self._client.post(
                f"{self._base_url}/bot{self._token}/{method}",
                json=params,
                timeout=self._timeout_s if timeout_s is None else timeout_s,
            )
        except httpx2.TimeoutException:
            error = TelegramNetworkError(f"Telegram {method} timed out.")
        except httpx2.HTTPError as exc:
            error = TelegramNetworkError(f"Telegram {method} failed ({type(exc).__name__}).")
        if error is not None:
            raise error

        try:
            payload = response.json()
        except ValueError:
            error = TelegramResponseError(
                f"Telegram {method} returned a non-JSON response (HTTP {response.status_code})."
            )
        if error is not None:
            raise error
        if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
            raise TelegramResponseError(f"Telegram {method} returned an unexpected response.")

        if not payload["ok"]:
            code = payload.get("error_code")
            description = payload.get("description")
            parameters = payload.get("parameters")
            retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
            raise TelegramAPIError(
                method,
                code if isinstance(code, int) else response.status_code,
                redact_token(str(description or ""))[:_MAX_DESCRIPTION],
                retry_after if isinstance(retry_after, int) else None,
            )

        return payload.get("result")

    def _call(
        self,
        method: str,
        params: dict[str, Any],
        model: type[M],
        *,
        timeout_s: float | None = None,
    ) -> M:
        result = self._request(method, params, timeout_s)
        error: TelegramError | None = None
        try:
            return model.model_validate(result)
        except ValidationError:
            error = TelegramResponseError(f"Telegram {method} returned an unexpected result.")
        raise error

    def get_me(self) -> TelegramUser:
        return self._call("getMe", {}, TelegramUser)

    def get_chat(self, chat_id: int | str) -> TelegramChat:
        return self._call("getChat", {"chat_id": chat_id}, TelegramChat)

    def get_chat_member(self, chat_id: int | str, user_id: int) -> TelegramChatMember:
        return self._call(
            "getChatMember", {"chat_id": chat_id, "user_id": user_id}, TelegramChatMember
        )

    # --- admin bot (V1.1b) ------------------------------------------------------------

    def get_updates(
        self, *, offset: int | None, timeout_s: int, allowed_updates: list[str]
    ) -> list[TelegramUpdate]:
        """Long polling. The HTTP timeout is the poll timeout plus `DEFAULT_TIMEOUT_S`."""
        params: dict[str, Any] = {"timeout": timeout_s, "allowed_updates": allowed_updates}
        if offset is not None:
            params["offset"] = offset
        result = self._request("getUpdates", params, timeout_s + DEFAULT_TIMEOUT_S)
        if not isinstance(result, list):
            raise TelegramResponseError("Telegram getUpdates returned an unexpected result.")
        updates: list[TelegramUpdate] = []
        for item in result:
            update_id = item.get("update_id") if isinstance(item, dict) else None
            if not isinstance(update_id, int):
                logger.warning("Telegram getUpdates: skipped an update without update_id")
                continue
            try:
                updates.append(TelegramUpdate.model_validate(item))
            except ValidationError:
                # Keep only the id: the caller confirms it, so one malformed update cannot
                # block the queue. Its content is not logged.
                logger.warning("Telegram getUpdates: update %d has an unexpected shape", update_id)
                updates.append(TelegramUpdate(update_id=update_id))
        return updates

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None,
    ) -> TelegramMessage:
        """`text` is HTML (every dynamic value escaped by the caller); no link previews."""
        params: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        if reply_to_message_id is not None:
            params["reply_parameters"] = {
                "message_id": reply_to_message_id,
                "allow_sending_without_reply": True,
            }
        return self._call("sendMessage", params, TelegramMessage)

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        """Without `reply_markup` the edited message has no inline keyboard."""
        params: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        self._request("editMessageText", params, None)

    def edit_message_reply_markup(
        self, chat_id: int, message_id: int, reply_markup: dict[str, Any] | None
    ) -> None:
        """`reply_markup=None` removes the inline keyboard."""
        params: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        self._request("editMessageReplyMarkup", params, None)

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        params: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text[:ANSWER_TEXT_MAX]
        if self._request("answerCallbackQuery", params, None) is not True:
            raise TelegramResponseError(
                "Telegram answerCallbackQuery returned an unexpected result."
            )
