"""`/imports/...` and `/events/{id}/evidence`: URL import (V1.2). No authentication here;
the application adds it globally. The import takes short pool checkouts
(`ConnFactoryDep`), so no connection is held while the page is fetched and extracted."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from fhc_api.common.audit import ADMIN_UI
from fhc_api.common.errors import error_responses
from fhc_api.common.pagination import DEFAULT_LIMIT, Limit, Offset
from fhc_api.db import ConnFactoryDep, DbConn
from fhc_api.importing.api_models import EvidenceOut, RunPage, UrlImportIn, UrlImportOut
from fhc_api.importing.service import UrlImporter


def build_import_router(get_importer: Callable[[], UrlImporter]) -> APIRouter:
    router = APIRouter(tags=["imports"])
    Importer = Annotated[UrlImporter, Depends(get_importer)]

    @router.post(
        "/imports/url",
        operation_id="import_event_url",
        response_model=UrlImportOut,
        responses=error_responses(409, 422),
    )
    def import_event_url(
        open_conn: ConnFactoryDep, importer: Importer, body: UrlImportIn
    ) -> UrlImportOut:
        """Creates a draft event from an event page, with field evidence. Synchronous and
        slow: usually 5-30 s, up to ~90 s when the local LLM loads its model (a cold
        start), so clients must wait at least 2 minutes.

        `duplicate` (200) when an event with the same normalized official URL exists;
        nothing is created. 422 when the URL is invalid or the page cannot be read (the
        run is recorded as failed). 409 when URL import is not configured. An LLM failure
        still creates the draft from the structured page data (`run.stats.llm_error`)."""
        return importer.import_url(open_conn, body.url, actor=ADMIN_UI)

    @router.get("/imports/runs", operation_id="list_import_runs", response_model=RunPage)
    def list_import_runs(
        conn: DbConn, importer: Importer, limit: Limit = DEFAULT_LIMIT, offset: Offset = 0
    ) -> RunPage:
        """Newest first. A run that stays `running` long after it started was interrupted."""
        return importer.list_runs(conn, limit=limit, offset=offset)

    @router.get(
        "/events/{event_id}/evidence",
        operation_id="get_event_evidence",
        response_model=EvidenceOut,
        responses=error_responses(404),
    )
    def get_event_evidence(conn: DbConn, importer: Importer, event_id: UUID) -> EvidenceOut:
        """Field evidence of the event's latest import; empty for events entered by hand."""
        return importer.evidence(conn, event_id)

    return router
