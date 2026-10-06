"""Audit of admin decisions (`app.admin_actions`, V1.1b).

Callers write the row inside the same transaction as the change it describes. `detail`
holds state changes only (statuses, whether a reason was given), never personal data
or free text.
"""

import re
from typing import Any, Literal
from uuid import UUID

from psycopg.types.json import Jsonb

from fhc_api.db import Conn

EntityType = Literal["event", "community_application", "team_application"]

ADMIN_UI = "admin_ui"
_ACTOR_RE = re.compile(r"admin_ui|telegram:[0-9]{1,20}")


def telegram_actor(user_id: int) -> str:
    return f"telegram:{user_id}"


def record(
    conn: Conn,
    *,
    actor: str,
    action: str,
    entity_type: EntityType,
    entity_id: UUID,
    detail: dict[str, Any],
) -> None:
    if not _ACTOR_RE.fullmatch(actor):  # the database checks it too
        raise ValueError("invalid audit actor")
    conn.execute(
        "insert into app.admin_actions (actor, action, entity_type, entity_id, detail)"
        " values (%s, %s, %s, %s, %s)",
        (actor, action, entity_type, entity_id, Jsonb(detail)),
    )
