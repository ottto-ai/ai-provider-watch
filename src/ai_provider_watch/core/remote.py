from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ai_provider_watch import __version__

DEFAULT_REMOTE_REF = "main"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_LIMIT_BYTES = 5_000_000
RAW_BASE_URL = "https://raw.githubusercontent.com/ottto-ai/ai-provider-watch"

REMOTE_ARTIFACTS: dict[str, str] = {
    "events": "data/feeds/events.json",
    "events.json": "data/feeds/events.json",
    "latest": "data/feeds/latest.json",
    "latest.json": "data/feeds/latest.json",
    "coverage": "data/feeds/coverage.json",
    "coverage.json": "data/feeds/coverage.json",
    "source-catalog": "data/feeds/source-catalog.json",
    "source-catalog.json": "data/feeds/source-catalog.json",
    "source_catalog": "data/feeds/source-catalog.json",
    "feed": "data/feeds/feed.json",
    "feed.json": "data/feeds/feed.json",
    "json-feed": "data/feeds/feed.json",
    "freshness": "data/feeds/freshness.json",
    "freshness.json": "data/feeds/freshness.json",
    "operations": "data/feeds/operations.json",
    "operations.json": "data/feeds/operations.json",
    "ndjson": "data/feeds/events.ndjson",
    "events.ndjson": "data/feeds/events.ndjson",
    "rss": "data/feeds/rss.xml",
    "rss.xml": "data/feeds/rss.xml",
}

JSON_REMOTE_ARTIFACTS = {
    key
    for key, path in REMOTE_ARTIFACTS.items()
    if path.endswith(".json")
}


class RemoteFeedError(RuntimeError):
    """Raised when a remote APW feed artifact cannot be fetched safely."""


def remote_artifact_path(name: str) -> str:
    normalized = name.strip()
    path = REMOTE_ARTIFACTS.get(normalized)
    if path is None:
        allowed = ", ".join(sorted(REMOTE_ARTIFACTS))
        raise ValueError(f"unknown remote feed {name!r}; expected one of: {allowed}")
    return path


def remote_raw_url(path: str, *, ref: str = DEFAULT_REMOTE_REF) -> str:
    normalized_ref = ref.strip()
    if not normalized_ref:
        raise ValueError("remote ref is required")
    normalized_path = path.strip().lstrip("/")
    if not normalized_path:
        raise ValueError("remote artifact path is required")
    if ".." in normalized_path.split("/"):
        raise ValueError("remote artifact path cannot contain '..'")
    return f"{RAW_BASE_URL}/{quote(normalized_ref, safe='')}/{quote(normalized_path, safe='/')}"


def fetch_remote_text(
    name: str,
    *,
    ref: str = DEFAULT_REMOTE_REF,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    limit_bytes: int = DEFAULT_LIMIT_BYTES,
) -> str:
    path = remote_artifact_path(name)
    url = remote_raw_url(path, ref=ref)
    request = Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "User-Agent": f"ai-provider-watch/{__version__}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(limit_bytes + 1)
    except HTTPError as exc:
        raise RemoteFeedError(f"remote feed fetch failed: HTTP {exc.code} {url}") from exc
    except (OSError, TimeoutError, URLError) as exc:
        raise RemoteFeedError(f"remote feed fetch failed: {exc}") from exc
    if len(payload) > limit_bytes:
        raise RemoteFeedError(f"remote feed exceeds byte limit: {limit_bytes}")
    return payload.decode("utf-8")


def fetch_remote_json(
    name: str,
    *,
    ref: str = DEFAULT_REMOTE_REF,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    limit_bytes: int = DEFAULT_LIMIT_BYTES,
) -> Any:
    text = fetch_remote_text(name, ref=ref, timeout=timeout, limit_bytes=limit_bytes)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RemoteFeedError(f"remote feed is not valid JSON: {name}") from exc
