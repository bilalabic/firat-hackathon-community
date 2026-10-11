"""Fetch the benchmark pages once with SafeFetcher (V1.2 part C).

    uv run python bench/fetch_pages.py [--only ID ...]

For each entry of bench/dataset.json: read the host's robots.txt (skip the page when it is
disallowed for our User-Agent), then GET the page through `SafeFetcher` and save the raw
bytes to bench/data/pages/<id>.html. At least DELAY_SECONDS between any two requests.
bench/data/ is gitignored: the pages are third-party content.
"""

import argparse
import json
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit

import httpx2

from fhc_api.common.http import (
    TIMEOUT_SECONDS,
    USER_AGENT,
    FetchError,
    SafeFetcher,
    check_url,
    is_public_address,
    system_resolver,
)

BENCH_DIR = Path(__file__).resolve().parent
DATA_DIR = BENCH_DIR / "data"
DELAY_SECONDS = 2.5
ROBOTS_MAX_CHARS = 512 * 1024

_last_request = 0.0


def _wait() -> None:
    global _last_request
    remaining = DELAY_SECONDS - (time.monotonic() - _last_request)
    if remaining > 0:
        time.sleep(remaining)
    _last_request = time.monotonic()


def _robots_text(origin: str) -> str | None:
    """robots.txt body, or None when the host has none.

    text/plain is outside the SafeFetcher allow-list, so this makes its own request,
    only after the host resolved to public addresses.
    """
    url = check_url(origin + "/robots.txt")
    host = url.raw_host.decode("ascii")
    try:
        addresses = system_resolver(host, 443 if url.scheme == "https" else 80)
    except OSError:
        return None
    if not addresses or not all(is_public_address(address) for address in addresses):
        return None
    _wait()
    try:
        response = httpx2.get(
            str(url),
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        )
    except httpx2.HTTPError:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if response.status_code != 200 or "html" in content_type:  # SPA fallbacks return HTML
        return None
    return response.text[:ROBOTS_MAX_CHARS]


def robots_allows(url: str, cache: dict[str, urllib.robotparser.RobotFileParser | None]) -> bool:
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in cache:
        text = _robots_text(origin)
        if text is None:
            cache[origin] = None
        else:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(text.splitlines())
            cache[origin] = parser
    cached = cache[origin]
    return True if cached is None else cached.can_fetch(USER_AGENT, url)


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--only", nargs="*", default=[])
    options = args.parse_args()
    entries = json.loads((BENCH_DIR / "dataset.json").read_text(encoding="utf-8"))
    pages = DATA_DIR / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    log_path = DATA_DIR / "fetch_log.json"
    log: dict[str, dict[str, object]] = (
        json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    )
    fetcher = SafeFetcher()
    robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
    for entry in entries:
        page_id, url = entry["id"], entry["url"]
        if options.only and page_id not in options.only:
            continue
        target = pages / f"{page_id}.html"
        if target.exists():
            print(f"{page_id}: already saved")
            continue
        if not robots_allows(url, robots):
            log[page_id] = {"url": url, "status": "robots_disallowed"}
            print(f"{page_id}: SKIPPED (robots.txt)")
            continue
        _wait()
        try:
            result = fetcher.fetch(url)
        except FetchError as exc:
            log[page_id] = {"url": url, "status": "error", "error": str(exc)}
            print(f"{page_id}: ERROR {exc}")
            continue
        log[page_id] = {
            "url": url,
            "final_url": result.url,
            "status": result.status_code,
            "content_type": result.content_type,
            "bytes": len(result.body),
        }
        if result.status_code == 200:
            target.write_bytes(result.body)
        print(f"{page_id}: {result.status_code} {len(result.body)} bytes")
    log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
