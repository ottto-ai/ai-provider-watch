from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_provider_watch.core.feeds import filter_events, load_events
from ai_provider_watch.core.io import repo_root
from ai_provider_watch.core.validation import validate

RESOURCES = ["apw://events/latest", "apw://events/{event_id}", "apw://providers/{provider}/events", "apw://indexes/kind/{kind}", "apw://sources/registry"]
TOOLS = ["apw_latest", "apw_diff", "apw_explain", "apw_check_repo_models", "apw_validate_event"]


def latest(root: Path | None = None, *, provider: str | None = None, risk: str | None = None) -> list[dict[str, Any]]:
    return filter_events(load_events(repo_root(root)), provider=provider, min_severity=risk)


def explain(event_id: str, root: Path | None = None) -> dict[str, Any] | None:
    return next((event for event in load_events(repo_root(root)) if event["id"] == event_id), None)


def validate_repo(root: Path | None = None) -> list[str]:
    return [issue.render() for issue in validate(repo_root(root))]
