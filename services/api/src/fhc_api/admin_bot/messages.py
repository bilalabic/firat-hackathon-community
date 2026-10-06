"""Admin bot message texts (HTML) and inline keyboards. English, like the admin UI (D-18).

Every dynamic value goes through `escape_html` (or `html_link`). Applications are
personal data: their messages carry the type, the first name and the chosen channel
only, never phone numbers, Telegram usernames or message text (D-21, KVKK).
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from fhc_api.admin_bot.codec import Action, Callback, Kind, encode
from fhc_api.common.audit import EntityType
from fhc_api.review.models import Signal
from fhc_api.telegram.formatting import escape_html, html_link, is_safe_http_url

Keyboard = dict[str, Any]

DISPLAY_TZ = ZoneInfo("Europe/Istanbul")
_TITLE_MAX = 160
_DETAIL_MAX = 160
_FIRST_NAME_MAX = 40
_SIGNAL_ICONS = {"pass": "✓", "fail": "✗", "warn": "⚠", "info": "·"}
_SIGNAL_LABELS = {
    "official_url_reachable": "Official URL",
    "registration_url_present": "Registration URL",
    "dates_coherent": "Dates",
    "deadline_missing": "Deadline set",
    "deadline_passed": "Deadline",
    "possible_duplicate": "Duplicates",
    "supporting_sources": "Sources",
}
_FORMATS = {"in_person": "In person", "online": "Online", "hybrid": "Hybrid"}
_APPLICATION_LABELS: dict[EntityType, str] = {
    "community_application": "Community application",
    "team_application": "Team application (Contribute)",
}
_CHANNELS = {"telegram": "Telegram", "whatsapp": "WhatsApp"}
_BUTTON_LABELS: dict[Action, str] = {
    "approve": "✅ Approve",
    "request_changes": "✏️ Request changes",
    "reject": "⛔ Reject",
    "reject_confirm": "⛔ Confirm reject",
    "publish": "🚀 Publish",
    "publish_confirm": "🚀 Confirm publish",
    "later": "Later",
    "cancel": "Cancel",
    "contacted": "Contacted",
    "accepted": "Accepted",
    "declined": "Declined",
    "spam": "Spam",
}
_KEYBOARD_LAYOUTS: dict[str, list[list[Action]]] = {
    "review": [["approve"], ["request_changes", "reject"]],
    "reject_confirm": [["reject_confirm", "cancel"]],
    "publish": [["publish", "later"]],
    "publish_confirm": [["publish_confirm", "cancel"]],
    "application": [["contacted", "accepted"], ["declined", "spam"]],
}

HELP_TEXT = (
    "<b>FHC admin bot</b>\n"
    "Events in review, approved events and new applications arrive here with buttons. "
    "Reject and Request changes ask for a reason: reply to the prompt message. "
    "Editing happens in the admin UI."
)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def first_name(full_name: str) -> str:
    parts = full_name.split()
    return _clip(parts[0], _FIRST_NAME_MAX) if parts else "(no name)"


def _date(value: object) -> str:
    return str(value) if value is not None else "not set"


def _event_lines(event: Mapping[str, Any]) -> list[str]:
    start, end = event.get("start_date"), event.get("end_date")
    dates = _date(start) if not end or end == start else f"{_date(start)} → {end}"
    place = ", ".join(str(part) for part in (event.get("city"), event.get("country")) if part)
    event_format = _FORMATS.get(event.get("format") or "", "format not set")
    lines = [
        f"Dates: {escape_html(dates)}",
        f"Deadline: {escape_html(_date(event.get('application_deadline')))}",
        f"Format: {escape_html(event_format + (f' · {place}' if place else ''))}",
    ]
    url = event.get("official_url") or ""
    if is_safe_http_url(url):
        host = urlsplit(url).hostname or url
        lines.append(f"Official: {html_link(url, _clip(host, 80))}")
    return lines


def event_header(event: Mapping[str, Any]) -> str:
    return f"<b>{escape_html(_clip(event['title'], _TITLE_MAX))}</b>"


def review_text(event: Mapping[str, Any], signals: Sequence[Signal]) -> str:
    checks = [
        f"{_SIGNAL_ICONS[signal.status]} {escape_html(_SIGNAL_LABELS[signal.key])}: "
        f"{escape_html(_clip(signal.detail, _DETAIL_MAX))}"
        for signal in signals
    ]
    return "\n".join(
        ["🔎 <b>Event in review</b>", event_header(event), *_event_lines(event), "", *checks]
    )


def publish_text(event: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "✅ <b>Approved, not published yet</b>",
            event_header(event),
            *_event_lines(event),
            "",
            "Publish it to the public site?",
        ]
    )


def application_header(entity_type: EntityType, row: Mapping[str, Any]) -> str:
    label = _APPLICATION_LABELS[entity_type]
    return f"<b>{escape_html(label)}</b> · {escape_html(first_name(row['full_name']))}"


def application_text(entity_type: EntityType, row: Mapping[str, Any]) -> str:
    lines = ["📥 <b>New application</b>", application_header(entity_type, row)]
    channel = row.get("preferred_channel")
    if channel:
        lines.append(f"Channel: {escape_html(_CHANNELS.get(channel, str(channel)))}")
    lines.append("Full details are in the admin UI.")
    return "\n".join(lines)


def header(entity_type: EntityType, row: Mapping[str, Any]) -> str:
    if entity_type == "event":
        return event_header(row)
    return application_header(entity_type, row)


def outcome_text(head: str, outcome: str, at: datetime | None = None) -> str:
    """The text a message is edited to once its buttons are no longer valid. `outcome`
    must already be escaped."""
    line = outcome
    if at is not None:
        line += f" ({at.astimezone(DISPLAY_TZ):%Y-%m-%d %H:%M} Istanbul)"
    return f"{head}\n\n{line}"


def reason_prompt_text(action: Action, head: str, ttl_minutes: int) -> str:
    verb = "rejecting" if action == "reject_confirm" else "requesting changes to"
    return (
        f"Reply to this message with the reason for {verb}:\n{head}\n\n"
        f"<i>The prompt expires in {ttl_minutes} minutes.</i>"
    )


def keyboard(
    layout: Kind | Literal["reject_confirm", "publish_confirm"],
    entity_type: EntityType,
    entity_id: UUID,
    token: str,
) -> Keyboard:
    """The buttons of a message kind, or of a confirmation step."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": _BUTTON_LABELS[action],
                    "callback_data": encode(Callback(action, entity_type, entity_id, token)),
                }
                for action in row
            ]
            for row in _KEYBOARD_LAYOUTS[layout]
        ]
    }


FORCE_REPLY: Keyboard = {"force_reply": True, "input_field_placeholder": "Reason"}
