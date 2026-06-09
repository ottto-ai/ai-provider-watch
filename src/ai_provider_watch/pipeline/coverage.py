from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ai_provider_watch import __version__
from ai_provider_watch.core.io import candidate_paths, event_paths, read_json
from ai_provider_watch.sources.registry import SourceDescriptor, load_source_descriptors

SOURCE_COVERAGE_SCHEMA_VERSION = "apw.source_coverage.v0"
SOURCE_STATE_PATH = Path("data/source-state/fingerprints.json")
STALE_SOURCE_STATE_HOURS = 72


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    if len(normalized) > 10 and normalized[10] == "t":
        normalized = f"{normalized[:10]}T{normalized[11:]}"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _provider_refs(root: Path) -> list[str]:
    providers = read_json(root / "registries" / "providers.json").get("providers", [])
    return [f"provider:{provider['id']}" for provider in providers if isinstance(provider.get("id"), str)]


def _parser_fixture_counts(root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for package_path in sorted((root / "sources").glob("*/source.json")):
        package = read_json(package_path)
        for fixture in package.get("parser_fixtures", []):
            if isinstance(fixture, dict) and isinstance(fixture.get("source_key"), str):
                counts[fixture["source_key"]] += 1
    return dict(counts)


def _source_state(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = root / SOURCE_STATE_PATH
    if not path.exists():
        return (
            {
                "path": str(SOURCE_STATE_PATH),
                "present": False,
                "source_count": 0,
                "latest_retrieved_at": None,
            },
            {},
        )
    payload = read_json(path)
    sources = payload.get("sources", {}) if isinstance(payload, dict) else {}
    source_map = {
        key: value
        for key, value in sources.items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    retrieved_at_values = [
        value.get("retrieved_at")
        for value in source_map.values()
        if isinstance(value.get("retrieved_at"), str)
    ]
    return (
        {
            "path": str(SOURCE_STATE_PATH),
            "present": True,
            "source_count": len(source_map),
            "latest_retrieved_at": max(retrieved_at_values) if retrieved_at_values else None,
        },
        source_map,
    )


def _events_by_provider(root: Path) -> tuple[Counter[str], dict[str, str]]:
    counts: Counter[str] = Counter()
    latest_dates: dict[str, str] = {}
    for path in event_paths(root):
        event = read_json(path)
        event_date = str(event.get("event_date") or "")
        for provider_ref in event.get("provider_refs", []):
            if not isinstance(provider_ref, str):
                continue
            counts[provider_ref] += 1
            latest_dates[provider_ref] = max(latest_dates.get(provider_ref, ""), event_date)
    return counts, latest_dates


def _candidate_backlog(root: Path) -> tuple[dict[str, Any], Counter[str], Counter[str]]:
    status_counts: Counter[str] = Counter()
    provider_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    total = 0
    for path in candidate_paths(root):
        candidate = read_json(path)
        if not isinstance(candidate, dict):
            continue
        total += 1
        status_counts[str(candidate.get("review_status") or "unknown")] += 1
        provider_refs = candidate.get("provider_refs", [])
        if isinstance(provider_refs, list):
            for provider_ref in provider_refs:
                if isinstance(provider_ref, str):
                    provider_counts[provider_ref] += 1
        source_keys = candidate.get("source_keys", [])
        if isinstance(source_keys, list):
            for source_key in source_keys:
                if isinstance(source_key, str):
                    source_counts[source_key] += 1
    return (
        {
            "total": total,
            "by_status": dict(sorted(status_counts.items())),
        },
        provider_counts,
        source_counts,
    )


def _source_status(source: SourceDescriptor, source_state: dict[str, dict[str, Any]]) -> str:
    if source.automation_status == "manual_review_only":
        return "manual_review_only"
    if source.automation_status == "blocked_pending_parser":
        return "blocked_pending_parser"
    if source.enabled and source.key in source_state:
        return "enabled_fetched"
    if source.enabled:
        return "enabled_missing_source_state"
    return "disabled"


def _source_row(
    source: SourceDescriptor,
    *,
    source_state: dict[str, dict[str, Any]],
    parser_fixture_counts: dict[str, int],
    candidate_counts: Counter[str],
) -> dict[str, Any]:
    state = source_state.get(source.key, {})
    return {
        "key": source.key,
        "provider_refs": source.provider_refs,
        "authority": source.authority,
        "source_type": source.source_type,
        "enabled": source.enabled,
        "automation_status": source.automation_status,
        "parser": source.parser,
        "coverage_status": _source_status(source, source_state),
        "parser_fixture_count": parser_fixture_counts.get(source.key, 0),
        "candidate_backlog_count": candidate_counts.get(source.key, 0),
        "source_state": {
            "present": source.key in source_state,
            "retrieved_at": state.get("retrieved_at") if isinstance(state.get("retrieved_at"), str) else None,
            "http_status": state.get("http_status") if isinstance(state.get("http_status"), int) else None,
        },
        "graduation_blockers": source.graduation_blockers,
    }


def _provider_rows(
    provider_refs: list[str],
    sources: list[SourceDescriptor],
    *,
    source_state: dict[str, dict[str, Any]],
    event_counts: Counter[str],
    latest_event_dates: dict[str, str],
    candidate_counts: Counter[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for provider_ref in provider_refs:
        provider_sources = [source for source in sources if provider_ref in source.provider_refs]
        enabled = [source for source in provider_sources if source.enabled]
        fetched_enabled = [source for source in enabled if source.key in source_state]
        blocked = [
            source
            for source in provider_sources
            if source.automation_status == "blocked_pending_parser"
        ]
        manual = [
            source
            for source in provider_sources
            if source.automation_status == "manual_review_only"
        ]
        rows.append(
            {
                "provider_ref": provider_ref,
                "source_count": len(provider_sources),
                "enabled_deterministic_source_count": len(enabled),
                "fetched_enabled_source_count": len(fetched_enabled),
                "manual_review_only_source_count": len(manual),
                "blocked_pending_parser_source_count": len(blocked),
                "missing_enabled_source_keys": [
                    source.key for source in enabled if source.key not in source_state
                ],
                "reviewed_event_count": event_counts.get(provider_ref, 0),
                "latest_event_date": latest_event_dates.get(provider_ref) or None,
                "candidate_backlog_count": candidate_counts.get(provider_ref, 0),
            }
        )
    return rows


def _warning(
    code: str,
    detail: str,
    *,
    severity: str = "warning",
    provider_ref: str | None = None,
    source_key: str | None = None,
) -> dict[str, Any]:
    warning: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "detail": detail,
    }
    if provider_ref:
        warning["provider_ref"] = provider_ref
    if source_key:
        warning["source_key"] = source_key
    return warning


def _coverage_warnings(
    sources: list[SourceDescriptor],
    *,
    source_state: dict[str, dict[str, Any]],
    source_state_summary: dict[str, Any],
    candidate_backlog: dict[str, Any],
    generated_at: str,
    stale_after_hours: int,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if not source_state_summary["present"]:
        warnings.append(_warning("source_state_missing", "source-state fingerprints are missing"))
    latest_retrieved_at = _parse_rfc3339(source_state_summary.get("latest_retrieved_at"))
    generated_at_dt = _parse_rfc3339(generated_at)
    if latest_retrieved_at and generated_at_dt:
        age = generated_at_dt - latest_retrieved_at
        if age > timedelta(hours=stale_after_hours):
            warnings.append(
                _warning(
                    "source_state_stale",
                    f"latest source-state retrieval is older than {stale_after_hours} hours",
                )
            )
    for source in sources:
        if source.enabled and source.key not in source_state:
            warnings.append(
                _warning(
                    "enabled_source_missing_source_state",
                    "enabled deterministic source has no source-state fingerprint",
                    provider_ref=source.provider_refs[0] if source.provider_refs else None,
                    source_key=source.key,
                )
            )
        if source.automation_status == "blocked_pending_parser":
            warnings.append(
                _warning(
                    "blocked_official_source",
                    "official source is registered but blocked until parser fixtures prove concrete deltas",
                    severity="info",
                    provider_ref=source.provider_refs[0] if source.provider_refs else None,
                    source_key=source.key,
                )
            )
    if candidate_backlog["total"]:
        warnings.append(
            _warning(
                "candidate_backlog_present",
                f"{candidate_backlog['total']} review candidate(s) are present outside reviewed events",
                severity="info",
            )
        )
    return warnings


def build_source_coverage_report(
    root: Path,
    *,
    created_at: str | None = None,
    stale_after_hours: int = STALE_SOURCE_STATE_HOURS,
) -> dict[str, Any]:
    generated_at = created_at or _utc_now()
    sources = load_source_descriptors(root, enabled_only=False)
    provider_refs = _provider_refs(root)
    source_state_summary, source_state = _source_state(root)
    parser_fixture_counts = _parser_fixture_counts(root)
    event_counts, latest_event_dates = _events_by_provider(root)
    candidate_backlog, candidate_provider_counts, candidate_source_counts = _candidate_backlog(root)
    enabled_sources = [source for source in sources if source.enabled]
    fetched_enabled_sources = [source for source in enabled_sources if source.key in source_state]
    source_rows = [
        _source_row(
            source,
            source_state=source_state,
            parser_fixture_counts=parser_fixture_counts,
            candidate_counts=candidate_source_counts,
        )
        for source in sources
    ]
    warnings = _coverage_warnings(
        sources,
        source_state=source_state,
        source_state_summary=source_state_summary,
        candidate_backlog=candidate_backlog,
        generated_at=generated_at,
        stale_after_hours=stale_after_hours,
    )
    event_count = sum(1 for _ in event_paths(root))
    latest_event_date = max(latest_event_dates.values()) if latest_event_dates else None
    fetched_ratio = (
        round(len(fetched_enabled_sources) / len(enabled_sources), 4)
        if enabled_sources
        else 1.0
    )
    return {
        "schema_version": SOURCE_COVERAGE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "package_version": __version__,
        "summary": {
            "provider_count": len(provider_refs),
            "source_count": len(sources),
            "enabled_deterministic_source_count": len(enabled_sources),
            "fetched_enabled_source_count": len(fetched_enabled_sources),
            "missing_enabled_source_count": len(enabled_sources) - len(fetched_enabled_sources),
            "fetched_enabled_source_ratio": fetched_ratio,
            "manual_review_only_source_count": sum(
                1 for source in sources if source.automation_status == "manual_review_only"
            ),
            "blocked_pending_parser_source_count": sum(
                1 for source in sources if source.automation_status == "blocked_pending_parser"
            ),
            "reviewed_event_count": event_count,
            "latest_event_date": latest_event_date,
            "candidate_backlog_count": candidate_backlog["total"],
            "warning_count": len(warnings),
        },
        "source_state": source_state_summary,
        "candidate_backlog": candidate_backlog,
        "providers": _provider_rows(
            provider_refs,
            sources,
            source_state=source_state,
            event_counts=event_counts,
            latest_event_dates=latest_event_dates,
            candidate_counts=candidate_provider_counts,
        ),
        "sources": source_rows,
        "warnings": warnings,
        "coverage_policy": "Coverage metadata contains counts, source keys, timestamps, and hashes only; no raw provider content.",
    }
