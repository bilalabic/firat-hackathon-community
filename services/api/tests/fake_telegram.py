"""An in-memory Bot API for admin bot and channel publishing tests (httpx2 MockTransport).
Never calls Telegram."""

import itertools
import json
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx2

from fhc_api.telegram.client import TelegramClient

# Obviously fake, format-valid token; leak checks look for ADMIN_LEAK_MARKER.
ADMIN_LEAK_MARKER = "FakeAdminBotSecretForTestsOnly_0123"
ADMIN_TOKEN = f"987654321:{ADMIN_LEAK_MARKER}"
BOT_ID = 987654321
ADMIN_ID = 1111
OTHER_ADMIN_ID = 2222
STRANGER_ID = 9999
# The channel bot (V1.1a publishing) is a different bot with its own token.
CHANNEL_LEAK_MARKER = "FakeChannelBotSecretForTestsOnly_456"
CHANNEL_TOKEN = f"123456789:{CHANNEL_LEAK_MARKER}"
CHANNEL_USERNAME = "@fhc_test_channel"
CHANNEL_CHAT_ID = -1001234567890


class FakeTelegram:
    def __init__(self, *, long_poll_s: float = 0.0) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.updates: list[dict[str, Any]] = []
        self.failures: dict[str, httpx2.Response] = {}
        # Called with the request body before the method is answered; may raise (e.g.
        # httpx2.ReadTimeout for a request that never gets an answer) or change the database
        # between the two transactions of a channel operation.
        self.hooks: dict[str, Callable[[dict[str, Any]], None]] = {}
        self.long_poll_s = long_poll_s
        self._message_ids = itertools.count(100)
        self._update_ids = itertools.count(5000)
        self._lock = threading.Lock()
        # Channel posts that exist (message id -> body of the last send/edit).
        self.channel_posts: dict[int, dict[str, Any]] = {}

    # --- transport -------------------------------------------------------------------

    def client(self) -> TelegramClient:
        transport = httpx2.MockTransport(self.handle)
        return TelegramClient(ADMIN_TOKEN, client=httpx2.Client(transport=transport))

    def channel_client(self) -> TelegramClient:
        """The channel bot (another token) against the same fake."""
        transport = httpx2.MockTransport(self.handle)
        return TelegramClient(CHANNEL_TOKEN, client=httpx2.Client(transport=transport))

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        body: dict[str, Any] = json.loads(request.content) if request.content else {}
        with self._lock:
            self.calls.append((method, body))
            failure = self.failures.get(method)
            hook = self.hooks.get(method)
        if hook is not None:
            hook(body)
        if failure is not None:
            return failure
        if method == "getMe":
            return _ok(
                {
                    "id": BOT_ID,
                    "is_bot": True,
                    "first_name": "FHC Admin",
                    "username": "fhc_admin_bot",
                }
            )
        if method == "getUpdates":
            return _ok(self._pending(body.get("offset")))
        if _is_channel(body.get("chat_id")):
            return self._channel(method, body)
        if method == "sendMessage":
            return _ok(self._message(body["chat_id"], next(self._message_ids), body["text"]))
        if method in ("editMessageText", "editMessageReplyMarkup"):
            return _ok(self._message(body["chat_id"], body["message_id"], body.get("text", "")))
        if method == "answerCallbackQuery":
            return _ok(True)
        return httpx2.Response(
            404, json={"ok": False, "error_code": 404, "description": "Not Found"}
        )

    def _channel(self, method: str, body: dict[str, Any]) -> httpx2.Response:
        """Channel posts: sendPhoto/sendMessage create one, edits need it to exist,
        deleteMessage removes it."""
        if method in ("sendPhoto", "sendMessage"):
            new_id = next(self._message_ids)
            with self._lock:
                self.channel_posts[new_id] = {"method": method, **body}
            return _ok(
                {
                    "message_id": new_id,
                    "date": int(time.time()),
                    "chat": {"id": CHANNEL_CHAT_ID, "type": "channel", "title": "FHC Test"},
                }
            )
        message_id = int(body.get("message_id", 0))
        with self._lock:
            exists = message_id in self.channel_posts
            if exists and method == "deleteMessage":
                del self.channel_posts[message_id]
            elif exists:
                self.channel_posts[message_id] = {
                    **self.channel_posts[message_id],
                    "last_edit": method,
                    **body,
                }
        if not exists:
            verb = "delete" if method == "deleteMessage" else "edit"
            return _fail(400, f"Bad Request: message to {verb} not found")
        if method == "deleteMessage":
            return _ok(True)
        chat = {"id": CHANNEL_CHAT_ID, "type": "channel"}
        return _ok({"message_id": message_id, "date": 1, "chat": chat})

    def _pending(self, offset: int | None) -> list[dict[str, Any]]:
        with self._lock:
            pending = [u for u in self.updates if offset is None or u["update_id"] >= offset]
        if not pending and self.long_poll_s:
            time.sleep(self.long_poll_s)
        return pending

    @staticmethod
    def _message(chat_id: int, message_id: int, text: str) -> dict[str, Any]:
        return {
            "message_id": message_id,
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private", "first_name": "Admin"},
            "from": {"id": BOT_ID, "is_bot": True, "first_name": "FHC Admin"},
            "text": text,
        }

    # --- scripted input --------------------------------------------------------------

    def _add(self, update: dict[str, Any]) -> int:
        with self._lock:
            update_id = next(self._update_ids)
            self.updates.append({"update_id": update_id, **update})
        return update_id

    def press(
        self, data: str, message_id: int, *, user_id: int = ADMIN_ID, chat_id: int | None = None
    ) -> int:
        chat = chat_id if chat_id is not None else user_id
        return self._add(
            {
                "callback_query": {
                    "id": f"cq{message_id}-{len(self.updates)}",
                    "from": {"id": user_id, "is_bot": False, "first_name": "Admin"},
                    "chat_instance": "1",
                    "data": data,
                    "message": {
                        "message_id": message_id,
                        "date": int(time.time()),
                        "chat": {"id": chat, "type": "private" if chat > 0 else "group"},
                    },
                }
            }
        )

    def reply(self, text: str, reply_to: int, *, user_id: int = ADMIN_ID) -> int:
        return self._add(
            {
                "message": {
                    "message_id": next(self._message_ids),
                    "date": int(time.time()),
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": user_id, "is_bot": False, "first_name": "Admin"},
                    "text": text,
                    "reply_to_message": {
                        "message_id": reply_to,
                        "date": int(time.time()),
                        "chat": {"id": user_id, "type": "private"},
                    },
                }
            }
        )

    # --- inspection ------------------------------------------------------------------

    def bodies(self, method: str) -> list[dict[str, Any]]:
        with self._lock:
            return [body for name, body in self.calls if name == method]

    def sent_about(self, entity_hex: str) -> list[dict[str, Any]]:
        """sendMessage bodies whose buttons refer to this entity."""
        return [
            body
            for body in self.bodies("sendMessage")
            if entity_hex in json.dumps(body.get("reply_markup", {}))
        ]

    def answers(self) -> list[str | None]:
        return [body.get("text") for body in self.bodies("answerCallbackQuery")]

    def clear_calls(self) -> None:
        with self._lock:
            self.calls.clear()


def _ok(result: object) -> httpx2.Response:
    return httpx2.Response(200, json={"ok": True, "result": result})


def _fail(code: int, description: str) -> httpx2.Response:
    return httpx2.Response(code, json={"ok": False, "error_code": code, "description": description})


def fail(code: int, description: str) -> httpx2.Response:
    """A scripted Bot API error for `FakeTelegram.failures[method]`."""
    return _fail(code, description)


def _is_channel(chat_id: object) -> bool:
    return chat_id in (CHANNEL_USERNAME, CHANNEL_CHAT_ID)


def buttons(body: dict[str, Any]) -> dict[str, str]:
    """Button label -> callback_data of a sendMessage/edit body."""
    rows = body.get("reply_markup", {}).get("inline_keyboard", [])
    return {button["text"]: button["callback_data"] for row in rows for button in row}
