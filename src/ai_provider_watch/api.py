"""Stable read-only consumer API for AI Provider Watch.

The CLI remains the primary operator surface. This module is the documented
Python import path for applications that want to read bundled or checkout APW
data without depending on internal package layout.
"""

# SPDX-FileCopyrightText: 2026 AI Provider Watch maintainers
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_provider_watch.core import io, remote
from ai_provider_watch.core.feeds import SEVERITY_RANK, filter_events
from ai_provider_watch.core.feeds import load_events as _load_events
from ai_provider_watch.core.validation import SCHEMA_FILES

RootLike = str | Path | None

JSON_FEEDS: dict[str, str] = {
    "events": "data/feeds/events.json",
    "latest": "data/feeds/latest.json",
    "coverage": "data/feeds/coverage.json",
    "feed": "data/feeds/feed.json",
    "json_feed": "data/feeds/feed.json",
    "json-feed": "data/feeds/feed.json",
    "freshness": "data/feeds/freshness.json",
    "operations": "data/feeds/operations.json",
}

TEXT_FEEDS: dict[str, str] = {
    "events.ndjson": "data/feeds/events.ndjson",
    "ndjson": "data/feeds/events.ndjson",
    "rss": "data/feeds/rss.xml",
    "rss.xml": "data/feeds/rss.xml",
}

__all__ = [
    "JSON_FEEDS",
    "TEXT_FEEDS",
    "data_root",
    "load_event",
    "load_events",
    "load_json_feed",
    "load_remote_events",
    "load_remote_json_feed",
    "load_remote_text_feed",
    "load_schema",
    "load_text_feed",
    "remote_feed_url",
]


def _validate_min_severity(min_severity: str | None) -> None:
    if min_severity is None:
        return
    if min_severity not in SEVERITY_RANK:
        allowed = ", ".join(SEVERITY_RANK)
        raise ValueError(f"unknown min_severity {min_severity!r}; expected one of: {allowed}")


def _validate_limit(limit: int | None) -> None:
    if limit is not None and limit < 1:
        raise ValueError("limit must be greater than zero")


def data_root(root: RootLike = None) -> Path:
    """Return a checkout root or bundled package-data root.

    Passing ``root`` requires that path to be an APW checkout or bundled
    package-data directory. Omitting it searches upward from the current working
    directory and then falls back to installed package data.
    """

    return io.repo_root(Path(root) if root is not None else None)


def load_events(
    *,
    root: RootLike = None,
    provider: str | None = None,
    min_severity: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load reviewed ProviderEvents sorted newest first.

    ``provider`` accepts either ``openai`` or ``provider:openai`` style values.
    ``min_severity`` must be one of ``info``, ``low``, ``medium``, ``high``, or
    ``critical``. Returned dictionaries are copies parsed from JSON files; APW
    may add optional fields in patch/minor releases, so consumers should ignore
    unknown keys.
    """

    _validate_min_severity(min_severity)
    _validate_limit(limit)

    events = filter_events(
        _load_events(data_root(root)),
        provider=provider,
        min_severity=min_severity,
    )
    return events[:limit] if limit is not None else events


def load_event(event_id: str, *, root: RootLike = None) -> dict[str, Any] | None:
    """Load one reviewed ProviderEvent by id, or ``None`` when absent."""

    if not event_id:
        raise ValueError("event_id is required")
    for event in _load_events(data_root(root)):
        if event.get("id") == event_id:
            return event
    return None


def load_json_feed(name: str = "events", *, root: RootLike = None) -> Any:
    """Load a generated JSON feed artifact by stable alias."""

    normalized = name.strip()
    path = JSON_FEEDS.get(normalized)
    if path is None:
        allowed = ", ".join(sorted(JSON_FEEDS))
        raise ValueError(f"unknown JSON feed {name!r}; expected one of: {allowed}")
    return io.read_json(data_root(root) / path)


def remote_feed_url(name: str = "events", *, ref: str = remote.DEFAULT_REMOTE_REF) -> str:
    """Return the public GitHub raw URL for one APW remote feed artifact."""

    return remote.remote_raw_url(remote.remote_artifact_path(name), ref=ref)


def load_remote_json_feed(
    name: str = "events",
    *,
    ref: str = remote.DEFAULT_REMOTE_REF,
    timeout: float = remote.DEFAULT_TIMEOUT_SECONDS,
    limit_bytes: int = remote.DEFAULT_LIMIT_BYTES,
) -> Any:
    """Fetch one reviewed APW JSON feed artifact from the public GitHub repo."""

    normalized = name.strip()
    if normalized not in remote.JSON_REMOTE_ARTIFACTS:
        allowed = ", ".join(sorted(remote.JSON_REMOTE_ARTIFACTS))
        raise ValueError(f"unknown remote JSON feed {name!r}; expected one of: {allowed}")
    return remote.fetch_remote_json(
        normalized,
        ref=ref,
        timeout=timeout,
        limit_bytes=limit_bytes,
    )


def load_remote_text_feed(
    name: str,
    *,
    ref: str = remote.DEFAULT_REMOTE_REF,
    timeout: float = remote.DEFAULT_TIMEOUT_SECONDS,
    limit_bytes: int = remote.DEFAULT_LIMIT_BYTES,
) -> str:
    """Fetch one reviewed APW text feed artifact from the public GitHub repo."""

    return remote.fetch_remote_text(
        name,
        ref=ref,
        timeout=timeout,
        limit_bytes=limit_bytes,
    )


def load_remote_events(
    *,
    ref: str = remote.DEFAULT_REMOTE_REF,
    provider: str | None = None,
    min_severity: str | None = None,
    limit: int | None = None,
    timeout: float = remote.DEFAULT_TIMEOUT_SECONDS,
    limit_bytes: int = remote.DEFAULT_LIMIT_BYTES,
) -> list[dict[str, Any]]:
    """Fetch reviewed ProviderEvents from a public GitHub ref or data tag."""

    _validate_min_severity(min_severity)
    _validate_limit(limit)
    events = load_remote_json_feed(
        "events",
        ref=ref,
        timeout=timeout,
        limit_bytes=limit_bytes,
    )
    if not isinstance(events, list):
        raise remote.RemoteFeedError("remote events feed is not a JSON array")
    filtered = filter_events(
        events,
        provider=provider,
        min_severity=min_severity,
    )
    return filtered[:limit] if limit is not None else filtered


def load_text_feed(name: str, *, root: RootLike = None) -> str:
    """Load a generated text feed artifact such as NDJSON or RSS."""

    normalized = name.strip()
    path = TEXT_FEEDS.get(normalized)
    if path is None:
        allowed = ", ".join(sorted(TEXT_FEEDS))
        raise ValueError(f"unknown text feed {name!r}; expected one of: {allowed}")
    return (data_root(root) / path).read_text(encoding="utf-8")


def load_schema(name: str, *, root: RootLike = None) -> dict[str, Any]:
    """Load a bundled JSON Schema by stable schema alias."""

    normalized = name.strip().removesuffix(".schema.json").replace("-", "_")
    filename = SCHEMA_FILES.get(normalized)
    if filename is None:
        allowed = ", ".join(sorted(SCHEMA_FILES))
        raise ValueError(f"unknown schema {name!r}; expected one of: {allowed}")
    return io.read_json(data_root(root) / "schemas" / filename)
