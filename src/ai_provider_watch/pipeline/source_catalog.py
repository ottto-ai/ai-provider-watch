from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_provider_watch import __version__
from ai_provider_watch.core.io import candidate_paths, event_paths, read_json
from ai_provider_watch.pipeline.coverage import build_source_coverage_report
from ai_provider_watch.sources.registry import load_source_descriptors

SOURCE_CATALOG_SCHEMA_VERSION = "apw.source_catalog.v0"
SOURCE_STATE_PATH = "data/source-state/fingerprints.json"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _source_registry_items(root: Path) -> dict[str, dict[str, Any]]:
    registry = read_json(root / "sources" / "registry.json")
    return {
        item["key"]: item
        for item in registry.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }


def _provider_items(root: Path) -> dict[str, dict[str, Any]]:
    providers = read_json(root / "registries" / "providers.json").get("providers", [])
    return {
        f"provider:{provider['id']}": provider
        for provider in providers
        if isinstance(provider, dict) and isinstance(provider.get("id"), str)
    }


def _surface_items(root: Path) -> dict[str, list[dict[str, Any]]]:
    surfaces_by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    surfaces = read_json(root / "registries" / "provider-surfaces.json").get("surfaces", [])
    for surface in surfaces:
        if not isinstance(surface, dict) or not isinstance(surface.get("provider_id"), str):
            continue
        surfaces_by_provider[f"provider:{surface['provider_id']}"].append(
            {
                "id": surface.get("id"),
                "kind": surface.get("kind"),
                "display_name": surface.get("display_name"),
                "url": surface.get("url") or surface.get("docs_url"),
            }
        )
    return {key: sorted(value, key=lambda item: str(item.get("id"))) for key, value in surfaces_by_provider.items()}


def _event_stats(root: Path) -> dict[str, Any]:
    provider_event_counts: Counter[str] = Counter()
    provider_latest_dates: dict[str, str] = {}
    source_event_counts: Counter[str] = Counter()
    source_latest_dates: dict[str, str] = {}
    event_kind_counts: Counter[str] = Counter()
    provider_event_kind_counts: dict[str, Counter[str]] = defaultdict(Counter)
    reviewed_event_count = 0

    for path in event_paths(root):
        event = read_json(path)
        reviewed_event_count += 1
        event_date = str(event.get("event_date") or "")
        event_kind = str(event.get("event_kind") or "unknown")
        event_kind_counts[event_kind] += 1

        for provider_ref in event.get("provider_refs", []):
            if not isinstance(provider_ref, str):
                continue
            provider_event_counts[provider_ref] += 1
            provider_event_kind_counts[provider_ref][event_kind] += 1
            provider_latest_dates[provider_ref] = max(
                provider_latest_dates.get(provider_ref, ""),
                event_date,
            )

        event_source_keys = {
            evidence.get("source_key")
            for evidence in event.get("evidence_refs", [])
            if isinstance(evidence, dict) and isinstance(evidence.get("source_key"), str)
        }
        for source_key in event_source_keys:
            source_event_counts[source_key] += 1
            source_latest_dates[source_key] = max(source_latest_dates.get(source_key, ""), event_date)

    return {
        "reviewed_event_count": reviewed_event_count,
        "provider_event_counts": provider_event_counts,
        "provider_latest_dates": provider_latest_dates,
        "source_event_counts": source_event_counts,
        "source_latest_dates": source_latest_dates,
        "event_kind_counts": event_kind_counts,
        "provider_event_kind_counts": provider_event_kind_counts,
    }


def _candidate_stats(root: Path) -> dict[str, Counter[str]]:
    provider_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for path in candidate_paths(root):
        candidate = read_json(path)
        if not isinstance(candidate, dict):
            continue
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

    return {
        "provider_counts": provider_counts,
        "source_counts": source_counts,
        "status_counts": status_counts,
    }


def _validation_status(coverage_row: dict[str, Any]) -> str:
    coverage_status = coverage_row.get("coverage_status")
    state = coverage_row.get("source_state", {})
    http_status = state.get("http_status") if isinstance(state, dict) else None
    fixture_count = int(coverage_row.get("parser_fixture_count") or 0)

    if coverage_status == "disabled":
        return "disabled"
    if coverage_status == "manual_review_only":
        return "manual_review_only"
    if coverage_status == "blocked_pending_parser":
        return "blocked_pending_parser"
    if coverage_status == "enabled_missing_source_state":
        return "missing_source_state"
    if isinstance(http_status, int) and not 200 <= http_status <= 399:
        return "fetch_error"
    if fixture_count <= 0:
        return "missing_parser_fixture"
    if coverage_status == "enabled_fetched":
        return "validated"
    return "unknown"


def _source_state_public(source_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(source_state),
        "retrieved_at": _optional_string(source_state.get("retrieved_at")),
        "http_status": source_state.get("http_status") if isinstance(source_state.get("http_status"), int) else None,
        "final_url": _optional_string(source_state.get("final_url")),
        "content_sha256": _optional_string(source_state.get("content_sha256")),
        "fingerprint": _optional_string(source_state.get("fingerprint")),
    }


def _build_source_rows(
    root: Path,
    *,
    coverage_by_key: dict[str, dict[str, Any]],
    raw_sources: dict[str, dict[str, Any]],
    event_stats: dict[str, Any],
    candidate_stats: dict[str, Counter[str]],
) -> list[dict[str, Any]]:
    source_state_payload = read_json(root / SOURCE_STATE_PATH) if (root / SOURCE_STATE_PATH).exists() else {}
    source_state = source_state_payload.get("sources", {}) if isinstance(source_state_payload, dict) else {}
    rows: list[dict[str, Any]] = []
    for source in load_source_descriptors(root, enabled_only=False):
        raw = raw_sources.get(source.key, {})
        coverage_row = coverage_by_key.get(source.key, {})
        validation_status = _validation_status(coverage_row)
        state = source_state.get(source.key, {}) if isinstance(source_state.get(source.key), dict) else {}
        rows.append(
            {
                "key": source.key,
                "provider_refs": source.provider_refs,
                "source_type": source.source_type,
                "authority": source.authority,
                "url": source.url,
                "cadence": _optional_string(raw.get("cadence")),
                "enabled": source.enabled,
                "automation_status": source.automation_status,
                "parser": source.parser,
                "validation_status": validation_status,
                "last_validated_at": _optional_string(state.get("retrieved_at")),
                "introduced_at": _optional_string(raw.get("introduced_at")),
                "introduced_ref": _optional_string(raw.get("introduced_ref")),
                "parser_fixture_count": int(coverage_row.get("parser_fixture_count") or 0),
                "reviewed_event_count": event_stats["source_event_counts"].get(source.key, 0),
                "latest_event_date": event_stats["source_latest_dates"].get(source.key) or None,
                "candidate_backlog_count": candidate_stats["source_counts"].get(source.key, 0),
                "impact_hints": source.impact_hints,
                "rate_limit": _optional_string(raw.get("rate_limit")),
                "robots_policy_note": _optional_string(raw.get("robots_policy_note")),
                "snapshot_policy": _optional_string(raw.get("snapshot_policy")),
                "license_note": _optional_string(raw.get("license_note")),
                "maintainers": _as_string_list(raw.get("maintainers")),
                "source_state": _source_state_public(state),
                "graduation_notes": source.graduation_notes,
                "graduation_blockers": source.graduation_blockers,
            }
        )
    return rows


def _build_provider_rows(
    *,
    providers: dict[str, dict[str, Any]],
    surfaces_by_provider: dict[str, list[dict[str, Any]]],
    source_rows: list[dict[str, Any]],
    event_stats: dict[str, Any],
    candidate_stats: dict[str, Counter[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for provider_ref, provider in sorted(providers.items()):
        provider_sources = [source for source in source_rows if provider_ref in source["provider_refs"]]
        source_types = sorted({source["source_type"] for source in provider_sources})
        cadences = sorted({source["cadence"] for source in provider_sources if source.get("cadence")})
        impact_hints = sorted(
            {
                impact
                for source in provider_sources
                for impact in source.get("impact_hints", [])
                if isinstance(impact, str)
            }
        )
        rows.append(
            {
                "provider_ref": provider_ref,
                "display_name": provider.get("display_name"),
                "provider_kind": provider.get("provider_kind"),
                "homepage_url": provider.get("homepage_url"),
                "aliases": _as_string_list(provider.get("aliases")),
                "source_count": len(provider_sources),
                "enabled_deterministic_source_count": sum(
                    1
                    for source in provider_sources
                    if source["enabled"] and source["automation_status"] == "enabled_deterministic"
                ),
                "validated_source_count": sum(
                    1 for source in provider_sources if source["validation_status"] == "validated"
                ),
                "source_types": source_types,
                "cadences": cadences,
                "impact_hints": impact_hints,
                "reviewed_event_count": event_stats["provider_event_counts"].get(provider_ref, 0),
                "latest_event_date": event_stats["provider_latest_dates"].get(provider_ref) or None,
                "candidate_backlog_count": candidate_stats["provider_counts"].get(provider_ref, 0),
                "event_kind_counts": dict(
                    sorted(event_stats["provider_event_kind_counts"].get(provider_ref, Counter()).items())
                ),
                "sources": [source["key"] for source in provider_sources],
                "surfaces": surfaces_by_provider.get(provider_ref, []),
            }
        )
    return rows


def build_source_catalog(root: Path, *, created_at: str | None = None) -> dict[str, Any]:
    generated_at = created_at or _utc_now()
    coverage = build_source_coverage_report(root, created_at=generated_at)
    coverage_by_key = {source["key"]: source for source in coverage.get("sources", [])}
    raw_sources = _source_registry_items(root)
    providers = _provider_items(root)
    surfaces_by_provider = _surface_items(root)
    events = _event_stats(root)
    candidates = _candidate_stats(root)
    source_rows = _build_source_rows(
        root,
        coverage_by_key=coverage_by_key,
        raw_sources=raw_sources,
        event_stats=events,
        candidate_stats=candidates,
    )
    provider_rows = _build_provider_rows(
        providers=providers,
        surfaces_by_provider=surfaces_by_provider,
        source_rows=source_rows,
        event_stats=events,
        candidate_stats=candidates,
    )
    validation_status_counts = Counter(source["validation_status"] for source in source_rows)
    source_type_counts = Counter(source["source_type"] for source in source_rows)
    cadence_counts = Counter(source["cadence"] or "unspecified" for source in source_rows)
    latest_source_state_retrieved_at = max(
        [
            source["source_state"]["retrieved_at"]
            for source in source_rows
            if source["source_state"]["retrieved_at"]
        ],
        default=None,
    )
    latest_event_date = max(
        [source["latest_event_date"] for source in source_rows if source["latest_event_date"]],
        default=None,
    )

    return {
        "schema_version": SOURCE_CATALOG_SCHEMA_VERSION,
        "generated_at": generated_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "package_version": __version__,
        "summary": {
            "provider_count": len(provider_rows),
            "source_count": len(source_rows),
            "enabled_deterministic_source_count": sum(
                1
                for source in source_rows
                if source["enabled"] and source["automation_status"] == "enabled_deterministic"
            ),
            "validated_source_count": validation_status_counts.get("validated", 0),
            "reviewed_event_count": events["reviewed_event_count"],
            "latest_event_date": latest_event_date,
            "candidate_backlog_count": sum(candidates["status_counts"].values()),
            "source_state_latest_retrieved_at": latest_source_state_retrieved_at,
            "source_type_counts": dict(sorted(source_type_counts.items())),
            "cadence_counts": dict(sorted(cadence_counts.items())),
            "validation_status_counts": dict(sorted(validation_status_counts.items())),
            "event_kind_counts": dict(sorted(events["event_kind_counts"].items())),
        },
        "providers": provider_rows,
        "sources": source_rows,
        "consumer_guidance": {
            "current_reviewed_feed": "Use apw remote latest --ref main or data/feeds/latest.json on the main branch for the freshest reviewed feed.",
            "immutable_feed": "Use signed data-YYYY.MM.DD tags for immutable reviewed snapshots.",
            "installed_package_snapshot": "Use apw latest for the reviewed snapshot bundled into the installed Python package.",
            "review_boundary": "Source fetches and generated candidates are review inputs only; publication requires reviewed ProviderEvent records.",
        },
        "catalog_policy": "source catalog contains source metadata, validation state, hashes, event counts, and backlog counts only; no raw provider content",
    }
