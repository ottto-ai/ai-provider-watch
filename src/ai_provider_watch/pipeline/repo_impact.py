from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ai_provider_watch.core.feeds import SEVERITY_RANK, filter_events, load_events
from ai_provider_watch.core.io import read_json
from ai_provider_watch.mcp.server import check_repo_models


def _parse_since(value: str) -> date:
    if value.endswith("d") and value[:-1].isdigit():
        return (datetime.now(UTC) - timedelta(days=int(value[:-1]))).date()
    return date.fromisoformat(value)


def _provider_aliases(root: Path) -> dict[str, str]:
    providers = read_json(root / "registries" / "providers.json").get("providers", [])
    aliases: dict[str, str] = {}
    for provider in providers:
        if not isinstance(provider, dict) or not isinstance(provider.get("id"), str):
            continue
        provider_ref = f"provider:{provider['id']}"
        aliases[provider["id"].lower()] = provider_ref
        aliases[provider_ref.lower()] = provider_ref
        for alias in provider.get("aliases", []):
            if isinstance(alias, str):
                aliases[alias.lower()] = provider_ref
    return aliases


def _app_aliases(root: Path) -> dict[str, str]:
    apps = read_json(root / "registries" / "agent-apps.json").get("agent_apps", [])
    aliases: dict[str, str] = {}
    for app in apps:
        if not isinstance(app, dict) or not isinstance(app.get("id"), str):
            continue
        app_ref = f"app:{app['id']}"
        aliases[app["id"].lower()] = app_ref
        aliases[app_ref.lower()] = app_ref
        for alias in app.get("aliases", []):
            if isinstance(alias, str):
                aliases[alias.lower()] = app_ref
    return aliases


def _canonical_match_refs(scan: dict[str, Any], root: Path) -> set[str]:
    provider_aliases = _provider_aliases(root)
    app_aliases = _app_aliases(root)
    refs: set[str] = set()
    matches = scan.get("matches", [])
    if not isinstance(matches, list):
        return refs
    for match in matches:
        if not isinstance(match, dict):
            continue
        kind = match.get("kind")
        ref = match.get("ref")
        if not isinstance(kind, str) or not isinstance(ref, str):
            continue
        if kind == "provider":
            refs.add(provider_aliases.get(ref.lower(), ref if ref.startswith("provider:") else f"provider:{ref}"))
        elif kind == "model":
            refs.add(ref if ref.startswith("model:") else f"model:{ref}")
        elif kind == "app":
            refs.add(app_aliases.get(ref.lower(), ref if ref.startswith("app:") else f"app:{ref}"))
    return refs


def _event_refs(event: dict[str, Any]) -> set[str]:
    refs = {ref for ref in event.get("provider_refs", []) if isinstance(ref, str)}
    detail = event.get("detail", {})
    if isinstance(detail, dict):
        for key in ("model_refs", "replacement_refs"):
            refs.update(ref for ref in detail.get(key, []) if isinstance(ref, str))
    for impact in event.get("impacts", []):
        if isinstance(impact, dict) and isinstance(impact.get("scope_ref"), str):
            refs.add(impact["scope_ref"])
    return refs


def repo_impact_report(
    apw_root: Path,
    repo_path: Path,
    *,
    since: str = "3650d",
    risk: str | None = None,
) -> dict[str, Any]:
    cutoff = _parse_since(since)
    scan = check_repo_models(repo_path, apw_root)
    matched_refs = _canonical_match_refs(scan, apw_root)
    events = [
        event
        for event in filter_events(load_events(apw_root), min_severity=risk)
        if date.fromisoformat(event["event_date"]) >= cutoff
    ]
    impacted: list[dict[str, Any]] = []
    for event in events:
        overlap = sorted(matched_refs & _event_refs(event))
        if not overlap:
            continue
        impacted.append(
            {
                "id": event["id"],
                "title": event["title"],
                "event_kind": event["event_kind"],
                "event_date": event["event_date"],
                "severity": event["severity"],
                "confidence": event["confidence"],
                "provider_refs": event.get("provider_refs", []),
                "matched_refs": overlap,
                "summary": event["summary"],
            }
        )
    return {
        "schema_version": "apw.repo_impact.v0",
        "repo_path": scan["repo_path"],
        "since": since,
        "risk": risk,
        "scanned_files": scan["scanned_files"],
        "matched_refs": sorted(matched_refs),
        "match_count": len(scan["matches"]),
        "events": impacted,
        "event_count": len(impacted),
        "untrusted_input_policy": scan["untrusted_input_policy"],
    }


def max_event_severity(report: dict[str, Any]) -> str | None:
    events = report.get("events", [])
    if not isinstance(events, list) or not events:
        return None
    return max(
        (event["severity"] for event in events if isinstance(event, dict) and event.get("severity") in SEVERITY_RANK),
        key=lambda value: SEVERITY_RANK[value],
        default=None,
    )
