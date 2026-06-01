from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path
from typing import Any

from ai_provider_watch import __version__
from ai_provider_watch.core.io import event_paths, read_json, write_json_text, write_ndjson_text

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


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


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _media_type(path: str) -> str:
    if path.endswith(".json"):
        return "application/json"
    if path.endswith(".ndjson"):
        return "application/x-ndjson"
    if path.endswith(".xml"):
        return "application/rss+xml"
    if path.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"


def build_artifacts(root: Path, release_id: str = "dev") -> dict[Path, str]:
    events = load_events(root)
    artifacts: dict[Path, str] = {
        Path("data/feeds/events.json"): write_json_text(events),
        Path("data/feeds/events.ndjson"): write_ndjson_text(events),
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

    checksums = {str(path): _checksum(text) for path, text in sorted(artifacts.items())}
    artifacts[Path(f"data/releases/{release_id}/checksums.txt")] = "".join(f"{checksum}  {path}\n" for path, checksum in sorted(checksums.items()))
    manifest_artifacts = [
        {"path": str(path), "media_type": _media_type(str(path)), "sha256": _checksum(text), "bytes": len(text.encode("utf-8"))}
        for path, text in sorted(artifacts.items())
    ]
    manifest = {
        "schema_version": "apw.release_manifest.v0",
        "release_id": release_id,
        "created_at": _event_time(events),
        "schema_versions": {"event": "apw.provider_event.v0", "event_detail": "apw.event_detail.v0", "release_manifest": "apw.release_manifest.v0"},
        "artifacts": manifest_artifacts,
        "checksums": {artifact["path"]: artifact["sha256"] for artifact in manifest_artifacts},
        "source_commit": None,
        "generated_by": f"ai-provider-watch {__version__}",
        "notes": "Deterministic development manifest.",
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
