"""Application status changes, shared by the admin API and the Telegram admin bot. Every
change is audited in the same transaction. Personal data: nothing here is logged."""

from uuid import UUID

from psycopg.rows import DictRow

from fhc_api.common import audit
from fhc_api.common.errors import not_found
from fhc_api.community import repository
from fhc_api.community.models import ApplicationStatus
from fhc_api.community.repository import ApplicationTable
from fhc_api.db import Conn

ENTITY_TYPES: dict[ApplicationTable, audit.EntityType] = {
    "community_applications": "community_application",
    "team_applications": "team_application",
}
_LABELS: dict[ApplicationTable, str] = {
    "community_applications": "community application",
    "team_applications": "team application",
}


def set_status(
    conn: Conn, table: ApplicationTable, row_id: UUID, status: ApplicationStatus, *, actor: str
) -> DictRow:
    with conn.transaction():
        current = repository.get_status(conn, table, row_id, for_update=True)
        if current is None:
            raise not_found(_LABELS[table])
        row = repository.set_status(conn, table, row_id, status)
        if row is None:  # pragma: no cover - the row is locked
            raise RuntimeError("application disappeared during update")
        audit.record(
            conn,
            actor=actor,
            action="set_status",
            entity_type=ENTITY_TYPES[table],
            entity_id=row_id,
            detail={"from": current, "to": status},
        )
    return row
