"""Reusable Pydantic field types. They mirror the database check constraints so that
bad input fails with 422 before it reaches Postgres.

Length bounds are set per field with `Field(min_length=..., max_length=...)`.
"""

import re
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BeforeValidator

from fhc_api.common.clock import is_valid_timezone

URL_MAX_LENGTH = 500


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _strip_or_none(value: object) -> object:
    """Forms send "" for an empty optional field; store it as NULL."""
    if isinstance(value, str):
        return value.strip() or None
    return value


def check_http_url(value: str, *, https_only: bool = False) -> str:
    """Accept only absolute http(s) URLs with a host and without credentials."""
    if any(ch.isspace() for ch in value):
        raise ValueError("URL must not contain whitespace")
    if len(value) > URL_MAX_LENGTH:
        raise ValueError(f"URL must be at most {URL_MAX_LENGTH} characters")
    try:
        parts = urlsplit(value)
        _ = parts.port  # raises ValueError for a malformed port
    except ValueError as exc:
        raise ValueError("malformed URL") from exc
    allowed = ("https",) if https_only else ("http", "https")
    if parts.scheme.lower() not in allowed:
        raise ValueError(f"URL scheme must be {' or '.join(allowed)}")
    if not parts.hostname:
        raise ValueError("URL must have a host")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URL must not contain credentials")
    return value


def _https_url(value: str) -> str:
    return check_http_url(value, https_only=True)


def _timezone(value: str) -> str:
    if not is_valid_timezone(value):
        raise ValueError("unknown IANA timezone")
    return value


_TAG_RE = re.compile(r"^[a-z0-9]+([-_.+#][a-z0-9]+)*$")
TAG_MAX_LENGTH = 40


def _tags(values: list[str]) -> list[str]:
    tags = [value.strip().lower() for value in values]
    for tag in tags:
        if len(tag) > TAG_MAX_LENGTH or not _TAG_RE.match(tag):
            raise ValueError(f"invalid tag {tag!r}: use lower-case letters, digits and - _ . + #")
    return list(dict.fromkeys(tags))  # drop duplicates, keep order


Text = Annotated[str, BeforeValidator(_strip)]
OptionalText = Annotated[str | None, BeforeValidator(_strip_or_none)]
HttpUrlStr = Annotated[str, BeforeValidator(_strip), AfterValidator(check_http_url)]
HttpsUrlStr = Annotated[str, BeforeValidator(_strip), AfterValidator(_https_url)]
OptionalHttpUrl = Annotated[HttpUrlStr | None, BeforeValidator(_strip_or_none)]
OptionalHttpsUrl = Annotated[HttpsUrlStr | None, BeforeValidator(_strip_or_none)]
Timezone = Annotated[str, BeforeValidator(_strip), AfterValidator(_timezone)]
Tags = Annotated[list[str], AfterValidator(_tags)]
