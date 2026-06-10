"""Stable read-only consumer API for AI Provider Watch.

The CLI remains the primary operator surface. This module is the documented
Python import path for applications that want to read bundled or checkout APW
data without depending on internal package layout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_provider_watch.core import io
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
    "load_schema",
    "load_text_feed",
]


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

    if min_severity is not None and min_severity not in SEVERITY_RANK:
        allowed = ", ".join(SEVERITY_RANK)
        raise ValueError(f"unknown min_severity {min_severity!r}; expected one of: {allowed}")
    if limit is not None and limit < 1:
        raise ValueError("limit must be greater than zero")

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
