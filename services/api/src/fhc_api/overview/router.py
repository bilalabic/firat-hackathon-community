"""Counters and keep-alive heartbeats for the admin Overview (LOCAL_ADMIN §1, D-19)."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fhc_api.db import DbConn
from fhc_api.events.repository import CLOSING_SQL, UPCOMING_SQL

router = APIRouter(tags=["overview"])

CLOSING_SOON_DAYS = 7
HEARTBEAT_SOURCES: tuple[Literal["vercel_cron", "github_actions"], ...] = (
    "vercel_cron",
    "github_actions",
)
HEARTBEAT_MAX_AGE = timedelta(hours=48)


class HeartbeatOut(BaseModel):
    source: Literal["vercel_cron", "github_actions"]
    last_seen_at: datetime | None
    stale: bool = Field(description="Never seen, or last seen more than 48 hours ago")


class OverviewOut(BaseModel):
    in_review: int
    published_upcoming: int = Field(description="Published, last day (end or start) >= today")
    closing_within_7_days: int = Field(description="Published, deadline within today..today+7")
    new_community_applications: int
    new_team_applications: int
    heartbeats: list[HeartbeatOut]


_COUNTS_SQL = f"""
select
  (select count(*) from app.events where status = 'in_review') as in_review,
  (select count(*) from app.events where {UPCOMING_SQL}) as published_upcoming,
  (select count(*) from app.events where {CLOSING_SQL}) as closing_within_7_days,
  (select count(*) from app.community_applications where status = 'new')
    as new_community_applications,
  (select count(*) from app.team_applications where status = 'new') as new_team_applications
"""  # noqa: S608 (constant fragments only)


@router.get("/overview", operation_id="get_overview", response_model=OverviewOut)
def get_overview(conn: DbConn) -> OverviewOut:
    counts = conn.execute(_COUNTS_SQL, {"days": CLOSING_SOON_DAYS}).fetchone() or {}
    seen = {
        row["source"]: row["last_seen_at"]
        for row in conn.execute("select source, last_seen_at from app.heartbeats").fetchall()
    }
    now = datetime.now(UTC)
    heartbeats = [
        HeartbeatOut(
            source=source,
            last_seen_at=seen.get(source),
            stale=source not in seen or now - seen[source] > HEARTBEAT_MAX_AGE,
        )
        for source in HEARTBEAT_SOURCES
    ]
    return OverviewOut(**counts, heartbeats=heartbeats)
