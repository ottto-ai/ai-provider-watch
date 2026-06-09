from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path
from typing import Any

from ai_provider_watch import __version__
from ai_provider_watch.core.io import event_paths, read_json, write_json_text, write_ndjson_text
from ai_provider_watch.pipeline.coverage import build_source_coverage_report

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
JSON_FEED_VERSION = "https://jsonfeed.org/version/1.1"
APW_HOME_URL = "https://github.com/ottto-ai/ai-provider-watch"
APW_RAW_MAIN_URL = "https://raw.githubusercontent.com/ottto-ai/ai-provider-watch/main"


def load_events(root: Path) -> list[dict[str, Any]]:
    events = [read_json(path) for path in event_paths(root)]
    return sorted(events, key=lambda event: (event.get("event_date", ""), event.get("observed_at", ""), event.get("id", "")), reverse=True)


def filter_events(events: list[dict[str, Any]], *, provider: str | None = None, min_severity: str | None = None) -> list[dict[str, Any]]:
    filtered = events
    if provider:
        provider_ref = provider if provider.startswith("provider:") else f"provider:{provider}"
        filtered = [event for event in filtered if provider_ref in event.get("provider_refs", [])]
    if min_severity:
        floor = SEVERITY_RANK[min_severity]
        filtered = [event for event in filtered if SEVERITY_RANK[event.get("severity", "info")] >= floor]
    return filtered


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    return {key: event[key] for key in ["id", "title", "event_kind", "event_date", "severity", "confidence", "provider_refs", "summary"]}


def _rss(events: list[dict[str, Any]]) -> str:
    items = []
    for event in events[:50]:
        items.append(
            "    <item>\n"
            f"      <guid isPermaLink=\"false\">{escape(event['id'])}</guid>\n"
            f"      <title>{escape(event['title'])}</title>\n"
            f"      <description>{escape(event['summary'])}</description>\n"
            f"      <category>{escape(event['event_kind'])}</category>\n"
            f"      <pubDate>{escape(_rss_pub_date(event['observed_at']))}</pubDate>\n"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">\n  <channel>\n'
        "    <title>AI Provider Watch</title>\n"
        "    <link>https://github.com/ottto-ai/ai-provider-watch</link>\n"
        "    <description>Reviewed AI-provider change events.</description>\n"
        + ("\n".join(items) + "\n" if items else "")
        + "  </channel>\n</rss>\n"
    )


def _json_feed_event_url(event: dict[str, Any]) -> str:
    return f"{APW_RAW_MAIN_URL}/data/events/{event['id']}.json"


def _json_feed_content(event: dict[str, Any]) -> str:
    providers = ", ".join(event.get("provider_refs", []))
    return (
        f"{event['summary']}\n\n"
        f"Kind: {event['event_kind']}\n"
        f"Severity: {event['severity']}\n"
        f"Confidence: {event['confidence']}\n"
        f"Providers: {providers}"
    )


def _json_feed_apw_extension(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": event["schema_version"],
        "event_id": event["id"],
        "event_kind": event["event_kind"],
        "lifecycle_status": event["lifecycle_status"],
        "provider_refs": event["provider_refs"],
        "event_date": event["event_date"],
        "effective_at": event.get("effective_at"),
        "migration_deadline": event.get("migration_deadline"),
        "severity": event["severity"],
        "confidence": event["confidence"],
        "source_authority": event["source_authority"],
        "evidence_refs": [
            {
                "source_key": evidence["source_key"],
                "url": evidence["url"],
                "authority": evidence["authority"],
                "content_sha256": evidence["content_sha256"],
                "snapshot_ref": evidence.get("snapshot_ref"),
                "selector": evidence.get("selector"),
            }
            for evidence in event.get("evidence_refs", [])
        ],
        "impacts": [
            {
                "scope_type": impact.get("scope_type"),
                "scope_ref": impact.get("scope_ref"),
                "impact_kind": impact.get("impact_kind"),
                "direction": impact.get("direction"),
                "severity": impact.get("severity"),
                "confidence": impact.get("confidence"),
            }
            for impact in event.get("impacts", [])
            if isinstance(impact, dict)
        ],
        "limitations": event.get("limitations", []),
    }


def _json_feed(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": JSON_FEED_VERSION,
        "title": "AI Provider Watch Reviewed Events",
        "home_page_url": APW_HOME_URL,
        "feed_url": f"{APW_RAW_MAIN_URL}/data/feeds/feed.json",
        "description": "Reviewed AI-provider change events for developer cost, quotas, model availability, defaults, deprecations, incidents, and migration risk.",
        "user_comment": "machine-readable reviewed APW events only. Provider pages and source text remain untrusted; this feed contains no raw provider content.",
        "authors": [
            {
                "name": "AI Provider Watch maintainers",
                "url": APW_HOME_URL,
            }
        ],
        "language": "en-US",
        "_apw": {
            "schema_version": "apw.provider_event.v0",
            "generated_by": f"ai-provider-watch {__version__}",
            "source": "reviewed ProviderEvent records",
            "policy": "contains reviewed APW event summaries and APW metadata only; no raw provider content.",
        },
        "items": [
            {
                "id": event["id"],
                "url": _json_feed_event_url(event),
                "external_url": event["evidence_refs"][0]["url"] if event.get("evidence_refs") else None,
                "title": event["title"],
                "content_text": _json_feed_content(event),
                "summary": event["summary"],
                "date_published": event["observed_at"],
                "date_modified": event["observed_at"],
                "tags": sorted(
                    {
                        event["event_kind"],
                        f"severity:{event['severity']}",
                        *event.get("provider_refs", []),
                        *event.get("tags", []),
                    }
                ),
                "_apw": _json_feed_apw_extension(event),
            }
            for event in events[:50]
        ],
    }


def _rss_pub_date(value: str) -> str:
    normalized = value.strip()
    if len(normalized) > 10 and normalized[10] == "t":
        normalized = f"{normalized[:10]}T{normalized[11:]}"
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return format_datetime(parsed.astimezone(UTC), usegmt=True)


def _event_time(events: list[dict[str, Any]]) -> str:
    if not events:
        return "1970-01-01T00:00:00Z"
    return max(event.get("observed_at", "") for event in events).replace("+00:00", "Z")


def _latest_event_date(events: list[dict[str, Any]]) -> str | None:
    if not events:
        return None
    return max(event.get("event_date", "") for event in events) or None


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _media_type(path: str) -> str:
    if path.endswith("feed.json"):
        return "application/feed+json"
    if path.endswith(".json"):
        return "application/json"
    if path.endswith(".ndjson"):
        return "application/x-ndjson"
    if path.endswith(".xml"):
        return "application/rss+xml"
    if path.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"


def _artifact_summary(path: Path, text: str) -> dict[str, Any]:
    return {
        "path": str(path),
        "media_type": _media_type(str(path)),
        "sha256": _checksum(text),
        "bytes": len(text.encode("utf-8")),
    }


def _source_state_summary(root: Path) -> dict[str, Any]:
    relative_path = Path("data/source-state/fingerprints.json")
    path = root / relative_path
    if not path.exists():
        return {
            "path": str(relative_path),
            "present": False,
            "sha256": None,
            "bytes": 0,
            "source_count": 0,
            "latest_retrieved_at": None,
        }

    text = path.read_text(encoding="utf-8")
    payload = read_json(path)
    sources = payload.get("sources", {}) if isinstance(payload, dict) else {}
    retrieved_at_values = [
        source.get("retrieved_at")
        for source in sources.values()
        if isinstance(source, dict) and isinstance(source.get("retrieved_at"), str)
    ]
    return {
        "path": str(relative_path),
        "present": True,
        "sha256": _checksum(text),
        "bytes": len(text.encode("utf-8")),
        "source_count": len(sources) if isinstance(sources, dict) else 0,
        "latest_retrieved_at": max(retrieved_at_values) if retrieved_at_values else None,
    }


def _build_freshness(
    root: Path,
    events: list[dict[str, Any]],
    artifacts: dict[Path, str],
    *,
    release_id: str,
    created_at: str,
) -> dict[str, Any]:
    summarized_artifacts = [
        _artifact_summary(path, text)
        for path, text in sorted(artifacts.items())
        if str(path).startswith(("data/feeds/", "data/indexes/"))
    ]
    return {
        "schema_version": "apw.feed_freshness.v0",
        "generated_at": created_at,
        "generated_by": f"ai-provider-watch {__version__}",
        "package_version": __version__,
        "release_id": release_id,
        "data_tag": release_id if release_id.startswith("data-") else None,
        "event_count": len(events),
        "latest_event_date": _latest_event_date(events),
        "latest_observed_at": _event_time(events),
        "source_state": _source_state_summary(root),
        "release_artifacts": {
            "manifest_path": f"data/releases/{release_id}/manifest.json",
            "checksums_path": f"data/releases/{release_id}/checksums.txt",
        },
        "feed_artifacts": summarized_artifacts,
        "freshness_policy": "Contains artifact hashes, counts, and timestamps only; no raw provider content.",
    }


def build_artifacts(
    root: Path,
    release_id: str = "dev",
    *,
    source_commit: str | None = None,
    created_at: str | None = None,
    notes: str | None = None,
) -> dict[Path, str]:
    events = load_events(root)
    resolved_created_at = created_at or _event_time(events)
    artifacts: dict[Path, str] = {
        Path("data/feeds/events.json"): write_json_text(events),
        Path("data/feeds/events.ndjson"): write_ndjson_text(events),
        Path("data/feeds/feed.json"): write_json_text(_json_feed(events)),
        Path("data/feeds/latest.json"): write_json_text([_compact_event(event) for event in events[:20]]),
        Path("data/feeds/rss.xml"): _rss(events),
    }

    for provider_ref in sorted({ref for event in events for ref in event.get("provider_refs", [])}):
        if provider_ref.startswith("provider:"):
            provider = provider_ref.split(":", 1)[1]
            artifacts[Path(f"data/indexes/provider/{provider}.json")] = write_json_text(filter_events(events, provider=provider))
    for kind in sorted({event["event_kind"] for event in events}):
        artifacts[Path(f"data/indexes/kind/{kind}.json")] = write_json_text([event for event in events if event["event_kind"] == kind])
    for severity in sorted({event["severity"] for event in events}, key=lambda item: SEVERITY_RANK[item]):
        artifacts[Path(f"data/indexes/severity/{severity}.json")] = write_json_text([event for event in events if event["severity"] == severity])

    coverage = build_source_coverage_report(root, created_at=resolved_created_at)
    artifacts[Path("data/feeds/coverage.json")] = write_json_text(coverage)

    freshness = _build_freshness(
        root,
        events,
        artifacts,
        release_id=release_id,
        created_at=resolved_created_at,
    )
    artifacts[Path("data/feeds/freshness.json")] = write_json_text(freshness)

    checksums = {str(path): _checksum(text) for path, text in sorted(artifacts.items())}
    artifacts[Path(f"data/releases/{release_id}/checksums.txt")] = "".join(f"{checksum}  {path}\n" for path, checksum in sorted(checksums.items()))
    manifest_artifacts = [
        _artifact_summary(path, text)
        for path, text in sorted(artifacts.items())
    ]
    manifest = {
        "schema_version": "apw.release_manifest.v0",
        "release_id": release_id,
        "created_at": resolved_created_at,
        "schema_versions": {
            "event": "apw.provider_event.v0",
            "event_detail": "apw.event_detail.v0",
            "feed_freshness": "apw.feed_freshness.v0",
            "json_feed": JSON_FEED_VERSION,
            "source_coverage": "apw.source_coverage.v0",
            "release_manifest": "apw.release_manifest.v0",
        },
        "artifacts": manifest_artifacts,
        "checksums": {artifact["path"]: artifact["sha256"] for artifact in manifest_artifacts},
        "source_commit": source_commit,
        "generated_by": f"ai-provider-watch {__version__}",
        "notes": notes or "Deterministic development manifest.",
    }
    artifacts[Path(f"data/releases/{release_id}/manifest.json")] = write_json_text(manifest)
    return artifacts


def write_artifacts(root: Path, artifacts: dict[Path, str]) -> None:
    for relative_path, text in artifacts.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def artifact_diffs(root: Path, artifacts: dict[Path, str]) -> list[str]:
    return [str(path) for path, expected in artifacts.items() if not (root / path).exists() or (root / path).read_text(encoding="utf-8") != expected]
