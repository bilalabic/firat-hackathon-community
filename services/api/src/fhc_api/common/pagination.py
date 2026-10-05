"""List responses share one envelope: items + total + the paging that produced them.

Subclass it per item type (`class EventPage(Page[EventOut])`) so the OpenAPI schema
gets a stable, readable name.
"""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
Offset = Annotated[int, Query(ge=0)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
