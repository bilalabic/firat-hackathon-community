"""Event rules: validation of merged state, slug generation and the state machine
(LOCAL_ADMIN §2). Every write runs inside its own transaction, so it has committed
when the function returns and the caller may trigger revalidation."""

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg.rows import DictRow

from fhc_api.common.errors import conflict, not_found, unprocessable
from fhc_api.common.http import BlockedUrlError, check_url, is_public_address
from fhc_api.common.normalize import SLUG_MAX_LENGTH, normalize_url, slugify
from fhc_api.db import Conn
from fhc_api.events import repository
from fhc_api.events.models import (
    EventAction,
    EventCreate,
    EventOut,
    EventStatus,
    EventTransition,
    EventUpdate,
)

# action -> (allowed source statuses, target status)
TRANSITIONS: dict[EventAction, tuple[frozenset[EventStatus], EventStatus]] = {
    "submit": (frozenset({"draft"}), "in_review"),
    "approve": (frozenset({"in_review"}), "approved"),
    "reject": (frozenset({"in_review"}), "rejected"),
    "request_changes": (frozenset({"in_review"}), "draft"),
    "publish": (frozenset({"approved"}), "published"),
    "unpublish": (frozenset({"published"}), "approved"),
    "archive": (frozenset({"published", "approved"}), "archived"),
    "reopen": (frozenset({"rejected", "archived"}), "draft"),
}

# Needed before review, and therefore before anything can be published.
REQUIRED_FOR_REVIEW = ("title", "summary", "official_url", "start_date", "format")
# Statuses whose data must keep passing the approval checks when edited.
GUARDED_STATUSES: frozenset[str] = frozenset({"approved", "published"})
INTERNAL_NOTES_MAX = 5000


def allowed_actions(status: str) -> list[EventAction]:
    return [action for action, (sources, _) in TRANSITIONS.items() if status in sources]


def to_out(row: Mapping[str, Any]) -> EventOut:
    return EventOut.model_validate({**row, "allowed_actions": allowed_actions(row["status"])})


# --- checks -------------------------------------------------------------------------


def _end_before_start(event: Mapping[str, Any]) -> list[str]:
    start, end = event.get("start_date"), event.get("end_date")
    return ["end_date is before start_date"] if start and end and end < start else []


def consistency_problems(event: Mapping[str, Any]) -> list[str]:
    """Rules that hold in every status (the database enforces most of them too)."""
    problems = _end_before_start(event)
    team_min, team_max = event.get("team_min"), event.get("team_max")
    if team_min is not None and team_max is not None and team_min > team_max:
        problems.append("team_min is greater than team_max")
    if event.get("prize_pool") is not None and not event.get("currency"):
        problems.append("currency is required when prize_pool is set")
    return problems


def missing_required_fields(event: Mapping[str, Any]) -> list[str]:
    return [field for field in REQUIRED_FOR_REVIEW if event.get(field) in (None, "")]


def date_problems(event: Mapping[str, Any]) -> list[str]:
    """Dates coherent: start <= end, and the deadline is not after the last event day
    (end_date, or start_date for a one-day event)."""
    problems = _end_before_start(event)
    start, end = event.get("start_date"), event.get("end_date")
    deadline = event.get("application_deadline")
    last_day = end or start
    if deadline and last_day and deadline > last_day:
        field = "end_date" if end else "start_date"
        problems.append(f"application_deadline is after {field}")
    return problems


def official_url_problem(url: str | None) -> str | None:
    """Static validity (no network): http(s), default port, public host."""
    if not url:
        return "official_url is missing"
    try:
        parsed = check_url(url)
    except BlockedUrlError as exc:
        return f"official_url is invalid: {exc}"
    host = parsed.host
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return "official_url must point to a public host"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host:
            return "official_url must use a fully qualified host name"
        return None
    if not is_public_address(host):
        return "official_url must point to a public host"
    return None


def approval_problems(event: Mapping[str, Any]) -> list[str]:
    problems = [f"{field} is required" for field in missing_required_fields(event)]
    problems += date_problems(event)
    if url_problem := official_url_problem(event.get("official_url")):
        problems.append(url_problem)
    return problems


def _guard(action: EventAction, event: Mapping[str, Any]) -> list[str]:
    if action == "submit":
        return [f"{field} is required" for field in missing_required_fields(event)]
    if action in ("approve", "publish"):
        return approval_problems(event)
    return []


# --- writes -------------------------------------------------------------------------


def _unique_slug(conn: Conn, title: str) -> str:
    base = slugify(title)
    if not repository.slug_exists(conn, base):
        return base
    suffix_number = 2
    while True:
        suffix = f"-{suffix_number}"
        candidate = base[: SLUG_MAX_LENGTH - len(suffix)].rstrip("-") + suffix
        if not repository.slug_exists(conn, candidate):
            return candidate
        suffix_number += 1


def _verified_at(values: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    new = values.get("verification_status")
    if new is None or new == current.get("verification_status"):
        return {}
    return {"verified_at": datetime.now(UTC) if new == "verified" else None}


def create_event(conn: Conn, data: EventCreate) -> DictRow:
    values = data.model_dump()
    if problems := consistency_problems(values):
        raise unprocessable("; ".join(problems))
    with conn.transaction():
        values["slug"] = _unique_slug(conn, data.title)
        values["official_url_normalized"] = normalize_url(data.official_url)
        values.update(_verified_at(values, {"verification_status": "unverified"}))
        return repository.insert(conn, values)


@dataclass(frozen=True)
class WriteResult:
    row: DictRow
    # True when the public site shows (or showed) this event and must be revalidated.
    affects_public_site: bool


def update_event(conn: Conn, event_id: UUID, data: EventUpdate) -> WriteResult:
    changes = data.model_dump(exclude_unset=True)
    with conn.transaction():
        current = repository.get(conn, event_id, for_update=True)
        if current is None:
            raise not_found("event")
        if not changes:
            return WriteResult(current, affects_public_site=False)
        if "official_url" in changes:
            changes["official_url_normalized"] = normalize_url(changes["official_url"])
        merged = {**current, **changes}
        if problems := consistency_problems(merged):
            raise unprocessable("; ".join(problems))
        if current["status"] in GUARDED_STATUSES and (problems := approval_problems(merged)):
            raise unprocessable(
                f"{current['status']} events must stay publishable: " + "; ".join(problems)
            )
        changes.update(_verified_at(changes, current))
        row = repository.update(conn, event_id, changes)
    return WriteResult(row, affects_public_site=row["status"] == "published")


def _append_note(notes: str | None, action: EventAction, reason: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"[{stamp}] {action}: {reason}"
    combined = f"{notes}\n{entry}" if notes else entry
    if len(combined) > INTERNAL_NOTES_MAX:
        raise unprocessable(f"internal_notes would exceed {INTERNAL_NOTES_MAX} characters")
    return combined


def transition_event(conn: Conn, event_id: UUID, body: EventTransition) -> WriteResult:
    action = body.action
    sources, target = TRANSITIONS[action]
    with conn.transaction():
        current = repository.get(conn, event_id, for_update=True)
        if current is None:
            raise not_found("event")
        status = current["status"]
        if status not in sources:
            raise conflict(f"cannot {action} an event in status {status}")
        if problems := _guard(action, current):
            raise conflict(f"cannot {action}: " + "; ".join(problems))
        if action == "reject" and not body.reason:
            raise unprocessable("reason is required to reject an event")

        values: dict[str, Any] = {"status": target}
        now = datetime.now(UTC)
        if action == "publish":
            values["published_at"] = now
        elif action == "archive":
            values["archived_at"] = now
        elif action == "reopen":
            values["archived_at"] = None
        if body.reason:
            values["internal_notes"] = _append_note(current["internal_notes"], action, body.reason)
        row = repository.update(conn, event_id, values)
    return WriteResult(row, affects_public_site="published" in (status, target))
